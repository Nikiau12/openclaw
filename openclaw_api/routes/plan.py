from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from openclaw_api.exchanges.registry import get_mexc_spot


router = APIRouter(tags=["plan"])


class PlanRequest(BaseModel):
    symbol: str


@router.post("/plan")
async def plan(req: PlanRequest):
    """
    Minimal real plan:
    - resolve symbol (BTC_USDT / btc-usdt / BTCUSDT -> BTCUSDT)
    - fetch 24h ticker summary
    - compute lightweight bias
    """
    try:
        p = get_mexc_spot()
        sym = await p.resolve_symbol(req.symbol)
        t = await p.summary_24h(sym)

        last = float(t["lastPrice"])
        change_pct = float(t["priceChangePercent"])  # MEXC returns ratio (0.044 == 4.4%)
        quote_vol = float(t.get("quoteVolume") or 0.0)

        # bias: dead simple for now
        if change_pct > 0.005:
            bias = "bullish"
        elif change_pct < -0.005:
            bias = "bearish"
        else:
            bias = "neutral"

        # placeholder levels (until ATR/EMA engine):
        high = float(t["highPrice"])
        low = float(t["lowPrice"])

        # naive trigger/invalidation:
        trigger = high if bias == "bullish" else (low if bias == "bearish" else None)
        invalidation = low if bias == "bullish" else (high if bias == "bearish" else None)

        return {
            "symbol_raw": req.symbol,
            "symbol": sym,
            "last": last,
            "change_24h_pct": change_pct * 100.0,
            "quote_volume_24h": quote_vol,
            "high_24h": high,
            "low_24h": low,
            "bias": bias,
            "trigger": trigger,
            "invalidation": invalidation,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
