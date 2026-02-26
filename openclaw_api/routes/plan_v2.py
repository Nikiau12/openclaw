from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from openclaw_api.exchanges.registry import get_mexc_spot


router = APIRouter(tags=["plan"])


class PlanRequest(BaseModel):
    symbol: str


@router.post("/plan/v2")
async def plan_v2(req: PlanRequest):
    """
    Returns the SAME contract as legacy /plan:
      { ok: true, message_html: "<b>...</b>" }
    but fills it with real MEXC 24h data.
    """
    try:
        p = get_mexc_spot()

        sym = await p.resolve_symbol(req.symbol)
        t = await p.summary_24h(sym)

        last = float(t["lastPrice"])
        change_pct_ratio = float(t["priceChangePercent"])  # 0.044 == 4.4%
        change_pct = change_pct_ratio * 100.0
        quote_vol = float(t.get("quoteVolume") or 0.0)
        high = float(t["highPrice"])
        low = float(t["lowPrice"])

        # bias (простая логика на сейчас)
        if change_pct > 0.5:
            bias = "BULLISH"
            icon = "🟩"
        elif change_pct < -0.5:
            bias = "BEARISH"
            icon = "🟥"
        else:
            bias = "NEUTRAL"
            icon = "🟦"

        # "уровни" пока наивные, чтобы было полезно без ATR/EMA
        # bullish: trigger=high_24h, invalidation=low_24h; bearish наоборот
        if bias == "BULLISH":
            trigger = high
            invalidation = low
        elif bias == "BEARISH":
            trigger = low
            invalidation = high
        else:
            trigger = None
            invalidation = None

        # аккуратный формат
        msg = (
            f"📌 <b>{req.symbol}</b> → <code>{sym}</code>\n"
            f"{icon} <b>Bias</b>: {bias}\n\n"
            f"💰 <b>Last</b>: <code>{last:.2f}</code>\n"
            f"📈 <b>24h</b>: <code>{change_pct:+.2f}%</code>\n"
            f"🌊 <b>QuoteVol</b>: <code>{quote_vol:,.0f}</code>\n"
            f"⬆️ <b>High</b>: <code>{high:.2f}</code>\n"
            f"⬇️ <b>Low</b>: <code>{low:.2f}</code>\n"
        )

        if trigger is not None and invalidation is not None:
            msg += (
                f"\n🎯 <b>Trigger</b>: <code>{trigger:.2f}</code>\n"
                f"🧯 <b>Invalidation</b>: <code>{invalidation:.2f}</code>\n"
            )

        msg += "\n🚨 <b>Риск-правило</b>: стоп обязателен.\n"

        return {"ok": True, "message_html": msg}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
