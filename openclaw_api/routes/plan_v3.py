from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from openclaw_api.routes.bias_v1 import compute_bias, normalize_symbol, normalize_interval, MEXC_BASE
from openclaw_api.indicators.candles import parse_mexc_klines, drop_unclosed_tail
from openclaw_api.analysis.structure import swings_from_candles
from openclaw_api.analysis.vol_profile import build_volume_profile


router = APIRouter(tags=["plan"])


class PlanRequest(BaseModel):
    symbol: str
    timeframes: list[str] = ["1h", "4h", "1d"]
    limit: int = 300


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


def _tf_label(tf: str) -> str:
    return tf.strip().upper()


def _regime(ema9: float, ema21: float, rsi14: float, last: float) -> str:
    # simple regime classifier: trend vs range
    # if EMAs close and RSI near 50 => range
    if last <= 0:
        return "UNKNOWN"
    spread = abs(ema9 - ema21) / last
    if spread < 0.003 and 45 <= rsi14 <= 55:
        return "RANGE"
    return "TREND"


async def _fetch_klines(client: httpx.AsyncClient, symbol: str, tf: str, limit: int) -> Dict[str, Any]:
    iv = normalize_interval(tf)
    r = await client.get(f"{MEXC_BASE}/api/v3/klines", params={"symbol": symbol, "interval": iv, "limit": limit})
    r.raise_for_status()
    raw = r.json()
    c = drop_unclosed_tail(parse_mexc_klines(raw))
    return {"tf": tf, "candles": c}


def _atr_for_tf(per_tf: List[Dict[str, Any]], tf: str) -> Optional[float]:
    for x in per_tf:
        if x.get("ok") and str(x.get("tf")).lower() == tf.lower():
            return float(x.get("atr14"))
    return None


def _ema21_for_tf(per_tf: List[Dict[str, Any]], tf: str) -> Optional[float]:
    for x in per_tf:
        if x.get("ok") and str(x.get("tf")).lower() == tf.lower():
            return float(x.get("ema21"))
    return None


@router.post("/plan")
async def plan_alias(req: PlanRequest):
    return await plan_v3(req)


@router.post("/plan/v3")
async def plan_v3(req: PlanRequest):
    try:
        sym = normalize_symbol(req.symbol)

        async with httpx.AsyncClient(timeout=15.0) as client:
            # 24h summary
            r = await client.get(f"{MEXC_BASE}/api/v3/ticker/24hr", params={"symbol": sym})
            r.raise_for_status()
            t = r.json()

            last = float(t["lastPrice"])
            change_pct = float(t["priceChangePercent"]) * 100.0
            quote_vol = float(t.get("quoteVolume") or 0.0)
            high = float(t["highPrice"])
            low = float(t["lowPrice"])

            # Bias engine (EMA/RSI/ATR per TF)
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

            # Drivers line (top weighted first)
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

            # --- Multi-TF ATR: prefer 4H for plan mechanics, fallback 1D, then 1H ---
            atr_4h = _atr_for_tf(per_tf, "4h")
            atr_1d = _atr_for_tf(per_tf, "1d")
            atr_1h = _atr_for_tf(per_tf, "1h")
            atr_ref = atr_4h or atr_1d or atr_1h

            # EMA21 dynamic level (4H)
            ema21_4h = _ema21_for_tf(per_tf, "4h")

            # Pull 4H candles for structure + volume profile (fast enough for one symbol)
            k4 = await _fetch_klines(client, sym, "4h", limit=min(200, req.limit))
            c4 = k4["candles"]

            swings = swings_from_candles(c4.h, c4.l, c4.c, left=3, right=3)
            vp = build_volume_profile(c4.h, c4.l, c4.c, c4.v, bins=48)

        # Regime (use 4H if available, else 1H)
        regime = "UNKNOWN"
        for x in ok_tfs:
            if str(x.get("tf")).lower() == "4h":
                regime = _regime(float(x["ema9"]), float(x["ema21"]), float(x["rsi14"]), float(x["last"]))
                break
        if regime == "UNKNOWN" and ok_tfs:
            x = ok_tfs[-1]
            regime = _regime(float(x["ema9"]), float(x["ema21"]), float(x["rsi14"]), float(x["last"]))

        # --- Level builder (Structure + VP + EMA21 + ATR buffer) ---
        # Buffers
        buf = 0.0
        if atr_ref is not None:
            # buffer grows slightly if regime is RANGE (more chop)
            buf = (0.25 if regime == "RANGE" else 0.15) * float(atr_ref)

        sh = swings.swing_high
        sl = swings.swing_low

        # Range bounds suggestion (if range)
        range_high = sh
        range_low = sl

        poc = vp.poc
        lvn_up = vp.lvn_above
        lvn_dn = vp.lvn_below

        def choose(x: Optional[float], fallback: Optional[float]) -> Optional[float]:
            return x if x is not None else fallback

        # directional levels
        trigger = None
        invalid = None
        scenarios = None

        if bias == "BULLISH":
            # Trigger: structure break first, then LVN above, then 24h high
            base_tr = choose(sh, choose(lvn_up, high))
            trigger = (float(base_tr) + buf) if base_tr is not None else None

            # Invalidation: structure low or EMA21 support
            base_iv = choose(sl, ema21_4h)
            invalid = (float(base_iv) - buf) if base_iv is not None else None

        elif bias == "BEARISH":
            # Trigger: break below swing low / LVN below / 24h low
            base_tr = choose(sl, choose(lvn_dn, low))
            trigger = (float(base_tr) - buf) if base_tr is not None else None

            # Invalidation: swing high or EMA21
            base_iv = choose(sh, ema21_4h)
            invalid = (float(base_iv) + buf) if base_iv is not None else None

        else:
            # NEUTRAL: two structural scenarios
            # LONG scenario
            long_tr_base = choose(sh, choose(lvn_up, high))
            long_iv_base = choose(sl, ema21_4h)

            # SHORT scenario
            short_tr_base = choose(sl, choose(lvn_dn, low))
            short_iv_base = choose(sh, ema21_4h)

            scenarios = {
                "long": {
                    "trigger": (float(long_tr_base) + buf) if long_tr_base is not None else None,
                    "invalidation": (float(long_iv_base) - buf) if long_iv_base is not None else None,
                },
                "short": {
                    "trigger": (float(short_tr_base) - buf) if short_tr_base is not None else None,
                    "invalidation": (float(short_iv_base) + buf) if short_iv_base is not None else None,
                },
            }

        # Message
        msg = (
            f"📌 <b>{req.symbol}</b> → <code>{sym}</code>\n"
            f"{icon} <b>Bias</b>: {bias}\n"
            f"{tf_line}"
            f"{reasons_line}"
            f"🧭 <b>Regime</b>: <code>{regime}</code>\n"
            f"🔩 <b>Structure(4H)</b>: "
            f"SH <code>{fmt_price(sh) if sh is not None else '—'}</code> | "
            f"SL <code>{fmt_price(sl) if sl is not None else '—'}</code>\n"
            f"📦 <b>VP(4H)</b>: "
            f"POC <code>{fmt_price(poc) if poc is not None else '—'}</code> | "
            f"LVN↑ <code>{fmt_price(lvn_up) if lvn_up is not None else '—'}</code> | "
            f"LVN↓ <code>{fmt_price(lvn_dn) if lvn_dn is not None else '—'}</code>\n\n"
            f"💰 <b>Last</b>: <code>{fmt_price(last)}</code>\n"
            f"📈 <b>24h</b>: <code>{change_pct:+.2f}%</code>\n"
            f"🌊 <b>QuoteVol</b>: <code>{quote_vol:,.0f}</code>\n"
            f"⬆️ <b>High</b>: <code>{fmt_price(high)}</code>\n"
            f"⬇️ <b>Low</b>: <code>{fmt_price(low)}</code>\n"
        )

        if scenarios is None:
            if trigger is not None and invalid is not None:
                msg += (
                    f"\n🎯 <b>Trigger</b>: <code>{fmt_price(trigger)}</code>\n"
                    f"🧯 <b>Invalidation</b>: <code>{fmt_price(invalid)}</code>\n"
                )
        else:
            lg = scenarios["long"]
            shh = scenarios["short"]
            msg += (
                f"\n🧭 <b>Scenarios</b> (structure+VP+EMA+ATR)\n"
                f"🟩 <b>LONG</b>  trigger: <code>{fmt_price(lg['trigger']) if lg['trigger'] is not None else '—'}</code> | "
                f"invalid: <code>{fmt_price(lg['invalidation']) if lg['invalidation'] is not None else '—'}</code>\n"
                f"🟥 <b>SHORT</b> trigger: <code>{fmt_price(shh['trigger']) if shh['trigger'] is not None else '—'}</code> | "
                f"invalid: <code>{fmt_price(shh['invalidation']) if shh['invalidation'] is not None else '—'}</code>\n"
            )

        msg += "\n🚨 <b>Риск-правило</b>: стоп обязателен.\n"
        return {"ok": True, "message_html": msg}

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"MEXC error: {e.response.status_code}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
