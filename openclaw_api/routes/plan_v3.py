from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from openclaw_api.routes.bias_v1 import compute_bias, normalize_symbol, MEXC_BASE


router = APIRouter(tags=["plan"])


class PlanRequest(BaseModel):
    symbol: str
    timeframes: list[str] = ["1h", "4h", "1d"]
    limit: int = 300


def _tf_label(tf: str) -> str:
    return tf.strip().upper()


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
            rel = ">" if ef > es else "<" if ef < es else "="
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
            f"💰 <b>Last</b>: <code>{last:.2f}</code>\n"
            f"📈 <b>24h</b>: <code>{change_pct:+.2f}%</code>\n"
            f"🌊 <b>QuoteVol</b>: <code>{quote_vol:,.0f}</code>\n"
            f"⬆️ <b>High</b>: <code>{high:.2f}</code>\n"
            f"⬇️ <b>Low</b>: <code>{low:.2f}</code>\n"
        )

        # scenario levels (ATR-based)
        if atr_ref is not None:
            k_trig = 0.5
            k_inv = 1.5

            if bias == "BULLISH":
                trigger = last + k_trig * atr_ref
                invalid = last - k_inv * atr_ref
                msg += (
                    f"\n🎯 <b>Trigger</b>: <code>{trigger:.2f}</code>\n"
                    f"🧯 <b>Invalidation</b>: <code>{invalid:.2f}</code>\n"
                )
            elif bias == "BEARISH":
                trigger = last - k_trig * atr_ref
                invalid = last + k_inv * atr_ref
                msg += (
                    f"\n🎯 <b>Trigger</b>: <code>{trigger:.2f}</code>\n"
                    f"🧯 <b>Invalidation</b>: <code>{invalid:.2f}</code>\n"
                )
            else:
                # neutral -> 2 scenarios
                lg_tr = last + k_trig * atr_ref
                lg_iv = last - k_inv * atr_ref
                sh_tr = last - k_trig * atr_ref
                sh_iv = last + k_inv * atr_ref
                msg += (
                    f"\n🧭 <b>Scenarios</b> (ATR-based)\n"
                    f"🟩 <b>LONG</b>  trigger: <code>{lg_tr:.2f}</code> | invalid: <code>{lg_iv:.2f}</code>\n"
                    f"🟥 <b>SHORT</b> trigger: <code>{sh_tr:.2f}</code> | invalid: <code>{sh_iv:.2f}</code>\n"
                )

        msg += "\n🚨 <b>Риск-правило</b>: стоп обязателен.\n"

        return {"ok": True, "message_html": msg}

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"MEXC error: {e.response.status_code}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
