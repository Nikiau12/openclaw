from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from openclaw_api.routes.bias_v1 import (
    compute_bias,
    normalize_symbol,
    normalize_interval,
    MEXC_BASE,
)

from openclaw_api.analysis.structure import Candle, detect_pivots, last_swings, bos_choch_note
from openclaw_api.analysis.vol_profile import build_vp


def fmt_price(x: float) -> str:
    # Human-friendly formatting for micro-priced assets (e.g., PEPE)
    ax = abs(x)
    if ax == 0:
        return "0"
    if ax >= 1000:
        s = f"{x:,.2f}"
    elif ax >= 1:
        s = f"{x:,.4f}"
    elif ax >= 0.01:
        s = f"{x:.6f}"
    elif ax >= 0.0001:
        s = f"{x:.8f}"
    else:
        s = f"{x:.10f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


router = APIRouter(tags=["plan"])


class PlanRequest(BaseModel):
    symbol: str
    timeframes: list[str] = ["1h", "4h", "1d"]
    limit: int = 300
    mode: str = "classic"  # classic (default) | structure


def _tf_label(tf: str) -> str:
    return tf.strip().upper()


def _to_candles_mexc_klines(rows) -> list[Candle]:
    out: list[Candle] = []
    for r in rows:
        # [openTime, open, high, low, close, volume, ...]
        out.append(Candle(
            ts=int(r[0]),
            o=float(r[1]),
            h=float(r[2]),
            l=float(r[3]),
            c=float(r[4]),
            v=float(r[5]),
        ))
    # no repaint: drop last unclosed candle
    return out[:-1] if len(out) > 2 else out


def _pick_atr(per_tf: list[dict]) -> float:
    """
    Primary ATR = 4H ATR(14), fallback 1D, fallback 1H.
    per_tf comes from compute_bias and contains atr14.
    """
    atr_1h = atr_4h = atr_1d = 0.0
    for x in per_tf:
        if not x.get("ok"):
            continue
        tf = str(x["tf"]).lower().strip()
        av = float(x["atr14"])
        if tf == "4h":
            atr_4h = av
        elif tf == "1d":
            atr_1d = av
        elif tf == "1h":
            atr_1h = av
    return atr_4h or atr_1d or atr_1h or 0.0


def _regime_from_4h(per_tf: list[dict]) -> tuple[str, float, float]:
    """
    TREND if abs(EMA9-EMA21)/last >= 0.003 OR RSI outside 45..55
    Returns: (kind, gap_ratio, rsi)
    """
    x4 = None
    for x in per_tf:
        if x.get("ok") and str(x.get("tf", "")).lower().strip() == "4h":
            x4 = x
            break
    if not x4:
        return ("RANGE", 0.0, 50.0)

    last = float(x4["last"])
    ema9 = float(x4["ema9"])
    ema21 = float(x4["ema21"])
    rsi = float(x4["rsi14"])
    gap_ratio = abs(ema9 - ema21) / max(1e-12, last)

    if gap_ratio >= 0.003 or (rsi < 45.0 or rsi > 55.0):
        return ("TREND", gap_ratio, rsi)
    return ("RANGE", gap_ratio, rsi)


@router.post("/plan")
async def plan_alias(req: PlanRequest):
    return await plan_v3(req)


@router.post("/plan/v3")
async def plan_v3(req: PlanRequest):
    try:
        sym = normalize_symbol(req.symbol)
        mode = (req.mode or "classic").strip().lower()

        # 24h summary
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(f"{MEXC_BASE}/api/v3/ticker/24hr", params={"symbol": sym})
            r.raise_for_status()
            t = r.json()

            last = float(t["lastPrice"])
            change_pct = float(t["priceChangePercent"]) * 100.0  # ratio -> %
            quote_vol = float(t.get("quoteVolume") or 0.0)
            high_24h = float(t["highPrice"])
            low_24h = float(t["lowPrice"])

        # real bias (multi-TF)
        b = await compute_bias(symbol=sym, timeframes=req.timeframes, limit=req.limit)
        bias = b["bias"]
        score_total = int(b["score_total"])
        weight_total = int(b["weight_total"])
        per_tf = b["per_tf"]

        icon = {"BULLISH": "🟩", "BEARISH": "🟥", "NEUTRAL": "🟦"}[bias]

        # TF score line
        parts = []
        for x in per_tf:
            if not x.get("ok"):
                continue
            parts.append(f"{_tf_label(x['tf'])}:{int(x['score']):+d}")
        tf_line = ""
        if parts:
            tf_line = f"📊 <b>TF</b>: {' | '.join(parts)} → <code>{score_total}/{weight_total}</code>\n"

        # Drivers line
        ok_tfs = [x for x in per_tf if x.get("ok")]
        ok_tfs.sort(key=lambda k: int(k.get("weight", 0)), reverse=True)
        reasons = []
        for x in ok_tfs[:2]:
            ef = float(x["ema9"])
            es = float(x["ema21"])
            rv = float(x["rsi14"])
            rel = "&gt;" if ef > es else "&lt;" if ef < es else "="
            reasons.append(f"{_tf_label(x['tf'])} EMA9{rel}EMA21, RSI {rv:.0f}")
        reasons_line = ""
        if reasons:
            reasons_line = f"🧩 <b>Drivers</b>: {' | '.join(reasons)}\n"

        msg = (
            f"📌 <b>{req.symbol}</b> → <code>{sym}</code>\n"
            f"{icon} <b>Bias</b>: {bias}\n"
            f"{tf_line}"
            f"{reasons_line}\n"
            f"💰 <b>Last</b>: <code>{fmt_price(last)}</code>\n"
            f"📈 <b>24h</b>: <code>{change_pct:+.2f}%</code>\n"
            f"🌊 <b>QuoteVol</b>: <code>{quote_vol:,.0f}</code>\n"
            f"⬆️ <b>High</b>: <code>{fmt_price(high_24h)}</code>\n"
            f"⬇️ <b>Low</b>: <code>{fmt_price(low_24h)}</code>\n"
        )

        # ===== classic (unchanged) =====
        if mode != "structure":
            atr_ref = None
            for x in ok_tfs:
                atr_ref = float(x["atr14"])
                break

            if atr_ref is not None:
                k_trig = 0.5
                k_inv = 1.5

                if bias == "BULLISH":
                    trigger = last + k_trig * atr_ref
                    invalid = last - k_inv * atr_ref
                    msg += (
                        f"\n🎯 <b>Trigger</b>: <code>{fmt_price(trigger)}</code>\n"
                        f"🧯 <b>Invalidation</b>: <code>{fmt_price(invalid)}</code>\n"
                    )
                elif bias == "BEARISH":
                    trigger = last - k_trig * atr_ref
                    invalid = last + k_inv * atr_ref
                    msg += (
                        f"\n🎯 <b>Trigger</b>: <code>{fmt_price(trigger)}</code>\n"
                        f"🧯 <b>Invalidation</b>: <code>{fmt_price(invalid)}</code>\n"
                    )
                else:
                    lg_tr = last + k_trig * atr_ref
                    lg_iv = last - k_inv * atr_ref
                    sh_tr = last - k_trig * atr_ref
                    sh_iv = last + k_inv * atr_ref
                    msg += (
                        f"\n🧭 <b>Scenarios</b> (ATR-based)\n"
                        f"🟩 <b>LONG</b>  trigger: <code>{fmt_price(lg_tr)}</code> | invalid: <code>{fmt_price(lg_iv)}</code>\n"
                        f"🟥 <b>SHORT</b> trigger: <code>{fmt_price(sh_tr)}</code> | invalid: <code>{fmt_price(sh_iv)}</code>\n"
                    )

            msg += "\n🚨 <b>Риск-правило</b>: стоп обязателен.\n"
            return {"ok": True, "message_html": msg}

        # ===== structure mode =====
        # 1) Fetch 4H klines for pivots + VP
        async with httpx.AsyncClient(timeout=12.0) as client:
            r4 = await client.get(
                f"{MEXC_BASE}/api/v3/klines",
                params={"symbol": sym, "interval": normalize_interval("4h"), "limit": req.limit},
            )
            r4.raise_for_status()
            c4 = _to_candles_mexc_klines(r4.json())

        if not c4:
            raise HTTPException(status_code=502, detail="No 4H candles for structure")

        # 2) Structure pivots
        piv = detect_pivots(c4, left=3, right=3)
        swings = last_swings(piv)
        sh = swings.swing_high.price if swings.swing_high else None
        sl = swings.swing_low.price if swings.swing_low else None
        struct_note = bos_choch_note(last_close=c4[-1].c, swings=swings, bias=bias)

        # 3) Volume Profile
        vp = build_vp(c4, bins=48, use_last_n=200)

        # 4) Regime (from 4H bias components)
        regime, gap_ratio, rsi4 = _regime_from_4h(per_tf)

        # 5) ATR + buffers
        atr4 = _pick_atr(per_tf)
        if atr4 <= 0:
            raise HTTPException(status_code=502, detail="ATR unavailable")

        if regime == "TREND":
            buf_tr = 0.15 * atr4
            buf_iv = 0.25 * atr4
        else:
            buf_tr = 0.25 * atr4
            buf_iv = 0.35 * atr4

        # 6) Choose bases (structure-first + fallbacks)
        # LONG bases
        long_tr_base = sh if sh is not None else (vp.lvn_above if vp.lvn_above is not None else high_24h)
        long_iv_base = sl if sl is not None else (None)

        # EMA21(4H) fallback from per_tf 4H
        ema21_4h = None
        for x in per_tf:
            if x.get("ok") and str(x.get("tf", "")).lower().strip() == "4h":
                ema21_4h = float(x["ema21"])
                break

        if long_iv_base is None:
            long_iv_base = ema21_4h if ema21_4h is not None else low_24h

        # SHORT bases
        short_tr_base = sl if sl is not None else (vp.lvn_below if vp.lvn_below is not None else low_24h)
        short_iv_base = sh if sh is not None else (ema21_4h if ema21_4h is not None else high_24h)

        # 7) Apply buffers (directional)
        long_trigger = float(long_tr_base) + buf_tr
        long_invalid = float(long_iv_base) - buf_iv

        short_trigger = float(short_tr_base) - buf_tr
        short_invalid = float(short_iv_base) + buf_iv

        # 8) Transparency lines
        msg += (
            f"\n🔩 <b>Structure(4H)</b>: "
            f"SH <code>{fmt_price(sh)}</code> | SL <code>{fmt_price(sl)}</code>\n"
            if (sh is not None and sl is not None) else
            f"\n🔩 <b>Structure(4H)</b>: insufficient pivots\n"
        )

        msg += f"🧠 <b>Note</b>: {struct_note}\n"

        msg += (
            f"📦 <b>VP(4H)</b>: POC <code>{fmt_price(vp.poc)}</code>"
            f" | LVN↑ <code>{fmt_price(vp.lvn_above) if vp.lvn_above is not None else '—'}</code>"
            f" | LVN↓ <code>{fmt_price(vp.lvn_below) if vp.lvn_below is not None else '—'}</code>\n"
        )

        msg += (
            f"🧊 <b>Buffer</b>: trig=<code>{fmt_price(buf_tr)}</code> inv=<code>{fmt_price(buf_iv)}</code> "
            f"({regime}) gap={gap_ratio:.4f} rsi={rsi4:.0f}\n"
        )

        # 9) Final levels with chosen-from
        msg += "\n🎯 <b>Levels</b>\n"

        def _src_long_tr() -> str:
            if sh is not None:
                return "swing_high"
            if vp.lvn_above is not None:
                return "LVN_above"
            return "24h_high"

        def _src_long_iv() -> str:
            if sl is not None:
                return "swing_low"
            if ema21_4h is not None:
                return "EMA21(4H)"
            return "24h_low"

        def _src_short_tr() -> str:
            if sl is not None:
                return "swing_low"
            if vp.lvn_below is not None:
                return "LVN_below"
            return "24h_low"

        def _src_short_iv() -> str:
            if sh is not None:
                return "swing_high"
            if ema21_4h is not None:
                return "EMA21(4H)"
            return "24h_high"

        msg += (
            f"🟩 <b>LONG</b> trigger: <code>{fmt_price(long_trigger)}</code> "
            f"(from { _src_long_tr() } + buf)\n"
            f"🟩 <b>LONG</b> invalid: <code>{fmt_price(long_invalid)}</code> "
            f"(from { _src_long_iv() } - buf)\n"
        )

        msg += (
            f"🟥 <b>SHORT</b> trigger: <code>{fmt_price(short_trigger)}</code> "
            f"(from { _src_short_tr() } - buf)\n"
            f"🟥 <b>SHORT</b> invalid: <code>{fmt_price(short_invalid)}</code> "
            f"(from { _src_short_iv() } + buf)\n"
        )

        if regime == "RANGE" and sh is not None and sl is not None:
            msg += f"\n📏 <b>Range</b>: <code>{fmt_price(sl)}</code> … <code>{fmt_price(sh)}</code>\n"

        msg += "\n🚨 <b>Риск-правило</b>: стоп обязателен.\n"
        return {"ok": True, "message_html": msg}

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"MEXC error: {e.response.status_code}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
