from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from openclaw_api.services.insight_service import run_insight

router = APIRouter(tags=["insight"])


class InsightRequest(BaseModel):
    symbol: str
    timeframes: list[str] = Field(default_factory=lambda: ["1h", "4h", "1d"])
    limit: int = 300


class InsightResponse(BaseModel):
    symbol: str
    verdict: str
    bias: str
    news_sentiment: str
    structure_note: str
    poc: float
    last_price: float
    conflicts: list[str]
    chart_only: bool


@router.post("/insight", response_model=InsightResponse)
async def insight(req: InsightRequest) -> InsightResponse:
    try:
        result = await run_insight(
            symbol=req.symbol,
            timeframes=req.timeframes,
            limit=req.limit,
        )
        return InsightResponse(**result.__dict__)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
