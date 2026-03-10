from __future__ import annotations

from fastapi import APIRouter, HTTPException
from openclaw_api.formatters.analyze_formatter import format_analyze_message
from pydantic import BaseModel
from typing import Optional
import httpx
from html import escape

from openclaw_api.routes.bias_v1 import (
    compute_bias,
    normalize_symbol,
    normalize_interval,
    MEXC_BASE,
)

from openclaw_api.analysis.structure import Candle, detect_pivots, last_swings, bos_choch_note
from openclaw_api.analysis.vol_profile import build_vp


def fmt_price(x: float) -> str:
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
        out.append(Candle(
            ts=int(r[0]),
            o=float(r[1]),
            h=float(r[2]),
            l=float(r[3]),
            c=float(r[4]),
            v=float(r[5]),
        ))
    return out[:-1] if len(out) > 2 else out


def _pick_atr(per_tf: list[dict]) -> float:
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


def _trend_dir_from_4h(per_tf: list[dict]) -> str:
    x4 = None
    for x in per_tf:
        if x.get("ok") and str(x.get("tf", "")).lower().strip() == "4h":
            x4 = x
            break
    if not x4:
        return "FLAT"
    ema9 = float(x4["ema9"])
    ema21 = float(x4["ema21"])
    if ema9 > ema21:
        return "UP"
    if ema9 < ema21:
        return "DOWN"
    return "FLAT"


@router.post("/plan")
async def plan_alias(req: PlanRequest):
    return await plan_v3(req)


@router.post("/plan/v3")
async def plan_v3(req: PlanRequest, mode: Optional[str] = None):
    try:
        sym = normalize_symbol(req.symbol)
        mode = (mode or req.mode or "classic").strip().lower()

        payload = {"symbol": sym, "mode": mode}

        # 24h summary
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(f"{MEXC_BASE}/api/v3/ticker/24hr", params={"symbol": sym})
            r.raise_for_status()
            t = r.json()

            last = float(t["lastPrice"])
            change_pct = float(t["priceChangePercent"]) * 100.0
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

        parts = []
        for x in per_tf:
            if not x.get("ok"):
                continue
            parts.append(f"{_tf_label(x['tf'])}:{int(x['score']):+d}")
        tf_line = ""
        if parts:
            tf_line = f"📊 <b>TF</b>: {' | '.join(parts)} → <code>{score_total}/{weight_total}</code>\n"

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

        bias_map = {
            "BULLISH": "Bullish",
            "BEARISH": "Bearish",
            "NEUTRAL": "Neutral",
        }

        summary_parts = [
            f"Last: {fmt_price(last)}",
            f"24h: {change_pct:+.2f}%",
        ]
        if tf_line:
            summary_parts.append(
                tf_line.replace("📊 <b>TF</b>: ", "")
                .replace("\n", "")
                .replace("<code>", "")
                .replace("</code>", "")
            )
        summary = " | ".join(summary_parts)

        why_items = reasons[:] if reasons else []
        if quote_vol:
            why_items.append(f"24h quote volume: {quote_vol:,.0f}")

        if change_pct >= 2.0:
            news_context = "Short-term flow is supportive; market tone is mildly bullish over the last 24h."
        elif change_pct <= -2.0:
            news_context = "Short-term flow is bearish; market tone is mildly negative over the last 24h."
        else:
            news_context = "Short-term headline/news proxy is neutral; no dominant directional pressure in the last 24h."

        analyze_data = {
            "symbol": sym,
            "summary": summary,
            "bias": bias_map.get(bias, bias.title()),
            "why": why_items,
            "key_levels": {
                "support": fmt_price(low_24h),
                "resistance": fmt_price(high_24h),
                "breakout_trigger": "N/A",
                "breakdown_trigger": "N/A",
            },
            "bullish_scenario": {
                "entry_logic": "N/A",
                "invalidation": "N/A",
                "targets": "N/A",
            },
            "bearish_scenario": {
                "entry_logic": "N/A",
                "invalidation": "N/A",
                "targets": "N/A",
            },
            "news_context": news_context,
            "risk_note": "Стоп обязателен.",
        }

        # ===== classic (formatter-backed) =====
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

                    analyze_data["key_levels"]["breakout_trigger"] = fmt_price(trigger)
                    analyze_data["bullish_scenario"] = {
                        "entry_logic": f"Break and hold above {fmt_price(trigger)}",
                        "invalidation": fmt_price(invalid),
                        "targets": [fmt_price(trigger + atr_ref), fmt_price(trigger + 2 * atr_ref)],
                    }

                elif bias == "BEARISH":
                    trigger = last - k_trig * atr_ref
                    invalid = last + k_inv * atr_ref

                    analyze_data["key_levels"]["breakdown_trigger"] = fmt_price(trigger)
                    analyze_data["bearish_scenario"] = {
                        "entry_logic": f"Break and hold below {fmt_price(trigger)}",
                        "invalidation": fmt_price(invalid),
                        "targets": [fmt_price(trigger - atr_ref), fmt_price(trigger - 2 * atr_ref)],
                    }

                else:
                    lg_tr = last + k_trig * atr_ref
                    lg_iv = last - k_inv * atr_ref
                    sh_tr = last - k_trig * atr_ref
                    sh_iv = last + k_inv * atr_ref

                    analyze_data["key_levels"]["breakout_trigger"] = fmt_price(lg_tr)
                    analyze_data["key_levels"]["breakdown_trigger"] = fmt_price(sh_tr)
                    analyze_data["bullish_scenario"] = {
                        "entry_logic": f"Break and hold above {fmt_price(lg_tr)}",
                        "invalidation": fmt_price(lg_iv),
                        "targets": [fmt_price(lg_tr + atr_ref), fmt_price(lg_tr + 2 * atr_ref)],
                    }
                    analyze_data["bearish_scenario"] = {
                        "entry_logic": f"Break and hold below {fmt_price(sh_tr)}",
                        "invalidation": fmt_price(sh_iv),
                        "targets": [fmt_price(sh_tr - atr_ref), fmt_price(sh_tr - 2 * atr_ref)],
                    }

            msg = format_analyze_message(analyze_data)
            return {"ok": True, "message_html": msg, "payload": payload}

        # ===== structure mode (guarded) =====
        payload = {
            "tf": "4H",
            "regime": None,
            "trend_dir": None,
            "range": {"low": None, "high": None},
            "levels": {
                "long": {"trigger": None, "invalid": None},
                "short": {"trigger": None, "invalid": None},
            },
            "vp": {"poc": None, "lvn": []},
            "buffers": {
                "trig": None,
                "inv": None,
                "atr": None,
                "trigger_atr_mult": None,
                "invalidation_atr_mult": None,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                r4 = await client.get(
                    f"{MEXC_BASE}/api/v3/klines",
                    params={"symbol": sym, "interval": normalize_interval("4h"), "limit": req.limit},
                )
                r4.raise_for_status()
                c4 = _to_candles_mexc_klines(r4.json())

            if not c4:
                raise ValueError("No 4H candles for structure")

            piv = detect_pivots(c4, left=3, right=3)
            swings = last_swings(piv)
            sh = swings.swing_high.price if swings.swing_high else None
            sl = swings.swing_low.price if swings.swing_low else None
            struct_note = escape(bos_choch_note(last_close=c4[-1].c, swings=swings, bias=bias), quote=False)

            struct_tag = ""
            if "BOS" in struct_note:
                struct_tag = "BOS"
            elif "CHOCH" in struct_note:
                struct_tag = "CHOCH"

            vp = build_vp(c4, bins=48, use_last_n=200)

            regime, gap_ratio, rsi4 = _regime_from_4h(per_tf)
            trend_dir = _trend_dir_from_4h(per_tf)
            payload["trend_dir"] = trend_dir

            atr4 = _pick_atr(per_tf)
            if atr4 <= 0:
                raise ValueError("ATR unavailable")

            if regime == "TREND":
                buf_tr = 0.15 * atr4
                buf_iv = 0.25 * atr4
            else:
                buf_tr = 0.25 * atr4
                buf_iv = 0.35 * atr4

            ema21_4h = None
            for x in per_tf:
                if x.get("ok") and str(x.get("tf", "")).lower().strip() == "4h":
                    ema21_4h = float(x["ema21"])
                    break

            # LONG bases
            long_tr_base = sh if sh is not None else (vp.lvn_above if vp.lvn_above is not None else high_24h)

            if sl is not None and ema21_4h is not None:
                long_iv_base = min(float(sl), float(ema21_4h))
            elif sl is not None:
                long_iv_base = float(sl)
            elif ema21_4h is not None:
                long_iv_base = float(ema21_4h)
            else:
                long_iv_base = float(low_24h)

            # SHORT bases
            short_tr_base = sl if sl is not None else (vp.lvn_below if vp.lvn_below is not None else low_24h)

            if sh is not None and ema21_4h is not None:
                short_iv_base = max(float(sh), float(ema21_4h))
            elif sh is not None:
                short_iv_base = float(sh)
            elif ema21_4h is not None:
                short_iv_base = float(ema21_4h)
            else:
                short_iv_base = float(high_24h)

            # Apply buffers
            long_trigger = float(long_tr_base) + buf_tr
            long_invalid = float(long_iv_base) - buf_iv

            short_trigger = float(short_tr_base) - buf_tr
            short_invalid = float(short_iv_base) + buf_iv

            # Transparency
            if sh is not None and sl is not None:
                msg += f"\n🔩 <b>Structure(4H)</b>: SH <code>{fmt_price(sh)}</code> | SL <code>{fmt_price(sl)}</code>\n"
            else:
                msg += "\n🔩 <b>Structure(4H)</b>: insufficient pivots\n"

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

            msg += "\n🎯 <b>Levels</b>\n"

            def _tagged(name: str) -> str:
                return f"{name} ({struct_tag})" if struct_tag and name.startswith("swing_") else name

            def _src_long_tr() -> str:
                if sh is not None:
                    return _tagged("swing_high")
                if vp.lvn_above is not None:
                    return "LVN_above"
                return "24h_high"

            def _src_long_iv() -> str:
                if sl is not None:
                    return _tagged("swing_low")
                if ema21_4h is not None:
                    return "EMA21(4H)"
                return "24h_low"

            def _src_short_tr() -> str:
                if sl is not None:
                    return _tagged("swing_low")
                if vp.lvn_below is not None:
                    return "LVN_below"
                return "24h_low"

            def _src_short_iv() -> str:
                if sh is not None:
                    return _tagged("swing_high")
                if ema21_4h is not None:
                    return "EMA21(4H)"
                return "24h_high"

            msg += (
                f"🟩 <b>LONG</b> trigger: <code>{fmt_price(long_trigger)}</code> (from {_src_long_tr()} + buf)\n"
                f"🟩 <b>LONG</b> invalid: <code>{fmt_price(long_invalid)}</code> (from {_src_long_iv()} - buf)\n"
            )

            msg += (
                f"🟥 <b>SHORT</b> trigger: <code>{fmt_price(short_trigger)}</code> (from {_src_short_tr()} - buf)\n"
                f"🟥 <b>SHORT</b> invalid: <code>{fmt_price(short_invalid)}</code> (from {_src_short_iv()} + buf)\n"
            )

            if regime == "RANGE" and sh is not None and sl is not None:
                msg += f"\n📏 <b>Range</b>: <code>{fmt_price(sl)}</code> … <code>{fmt_price(sh)}</code>\n"

            # machine payload (for Dexter reasoning)
            payload["regime"] = regime
            payload["buffers"]["atr"] = float(atr4)
            payload["buffers"]["trig"] = float(buf_tr)
            payload["buffers"]["inv"] = float(buf_iv)
            payload["buffers"]["trigger_atr_mult"] = 0.15 if regime == "TREND" else 0.25
            payload["buffers"]["invalidation_atr_mult"] = 0.25 if regime == "TREND" else 0.35

            payload["levels"]["long"]["trigger"] = float(long_trigger)
            payload["levels"]["long"]["invalid"] = float(long_invalid)
            payload["levels"]["short"]["trigger"] = float(short_trigger)
            payload["levels"]["short"]["invalid"] = float(short_invalid)

            payload["vp"]["poc"] = float(vp.poc)
            lvn = []
            if vp.lvn_above is not None:
                lvn.append(float(vp.lvn_above))
            if vp.lvn_below is not None:
                lvn.append(float(vp.lvn_below))
            payload["vp"]["lvn"] = lvn

            if sh is not None:
                payload["range"]["high"] = float(sh)
            if sl is not None:
                payload["range"]["low"] = float(sl)

        except Exception as e:
            # DO NOT break API startup/healthchecks because of structure mode.
            msg += f"\n⚠️ <b>Structure mode error</b>: <code>{str(e)}</code>\n"
            payload["error"] = str(e)

        msg += "\n🚨 <b>Риск-правило</b>: стоп обязателен.\n"
        return {"ok": True, "message_html": msg, "payload": payload}

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"MEXC error: {e.response.status_code}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
