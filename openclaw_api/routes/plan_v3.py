from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from openclaw_api.routes.bias_v1 import compute_bias, normalize_symbol, MEXC_BASE



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
    # trim trailing zeros
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s

router = APIRouter(tags=["plan"])


class PlanRequest(BaseModel):
    symbol: str
    timeframes: list[str] = ["1h", "4h", "1d"]
    limit: int = 300


def _tf_label(tf: str) -> str:
    return tf.strip().upper()



@router.post("/plan")
async def plan_alias(req: PlanRequest):
    # backward-compatible alias -> current implementation
    return await plan_v3(req)


@router.post("/plan/v3")
async def plan_v3(req: PlanRequest):
    try:
        sym = normalize_symbol(req.symbol)

        # 24h summary
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(f"{MEXC_BASE}/api/v3/ticker/24hr", params={"symbol": sym})
            r.raise_for_status()
            t = r.json()

        last = float(t["lastPrice"])
        change_pct = float(t["priceChangePercent"]) * 100.0  # ratio -> %
        quote_vol = float(t.get("quoteVolume") or 0.0)
        high = float(t["highPrice"])
        low = float(t["lowPrice"])

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

        # ATR reference from highest-weight valid TF
        atr_ref = None
        for x in ok_tfs:
            atr_ref = float(x["atr14"])
            break

        msg = (
            f"📌 <b>{req.symbol}</b> → <code>{sym}</code>\n"
            f"{icon} <b>Bias</b>: {bias}\n"
            f"{tf_line}"
            f"{reasons_line}\n"
            f"💰 <b>Last</b>: <code>{fmt_price(last)}</code>\n"
            f"📈 <b>24h</b>: <code>{change_pct:+.2f}%</code>\n"
            f"🌊 <b>QuoteVol</b>: <code>{quote_vol:,.0f}</code>\n"
            f"⬆️ <b>High</b>: <code>{fmt_price(high)}</code>\n"
            f"⬇️ <b>Low</b>: <code>{fmt_price(low)}</code>\n"
        )

        # scenario levels (ATR-based)
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
                # neutral -> 2 scenarios
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

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"MEXC error: {e.response.status_code}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
