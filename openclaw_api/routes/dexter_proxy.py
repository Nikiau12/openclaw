from __future__ import annotations

import os
import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from openclaw_api.routes.plan_v3 import plan_v3, PlanRequest
import httpx

router = APIRouter(prefix="/dexter", tags=["dexter"])


class DexterRunRequest(BaseModel):
    query: str
    analysis: Optional[bool] = None


def _base() -> str:
    return (os.getenv("DEXTER_AGENT_URL") or "").strip().rstrip("/")


def guess_symbol(query: str) -> str:
    q = (query or "").upper()
    # Simple extraction: look for e.g. BTCUSDT or BTC_USDT
    m = re.search(r"\b[A-Z]{2,10}(?:USDT|USD|BTC|ETH)\b|\b[A-Z]{2,10}[_-][A-Z]{3,6}\b", q)
    if not m:
        return "BTC_USDT"
    raw = m.group(0)
    if "_" in raw or "-" in raw:
        return raw.replace("-", "_")
    if raw.endswith("USDT"):
        return raw[:-4] + "_USDT"
    return raw


@router.get("/health")
async def dexter_health():
    base = _base()
    if not base:
        raise HTTPException(status_code=503, detail="DEXTER_AGENT_URL not configured")
    try:
        async with httpx.AsyncClient(timeout=50.0) as client:
            r = await client.get(f"{base}/health")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/run")
async def dexter_run(req: DexterRunRequest, analysis: Optional[str] = Query(default=None)):
    base = _base()
    if not base:
        raise HTTPException(status_code=503, detail="DEXTER_AGENT_URL not configured")

    q = (req.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query is empty")

    try:
        # analysis flag: body has priority, then query param
        flag = bool(req.analysis) if req.analysis is not None else (str(analysis).strip().lower() in ("1","true","yes","y"))
        async with httpx.AsyncClient(timeout=50.0) as client:
            r = await client.post(f"{base}/run", json={"query": q, "analysis": flag})
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        sym = guess_symbol(q)
        plan = await plan_v3(PlanRequest(symbol=sym, mode="structure"))
        msg = (plan.get("message_html") if isinstance(plan, dict) else None) or "<i>Plan unavailable</i>"
        return {
            "ok": True,
            "message_html": msg,
            "raw": {
                "mode": "fallback_plan_only",
                "error": f"dexter_http_{e.response.status_code}",
                "symbol": sym,
                "plan": plan,
            },
        }
    except Exception as e:
        sym = guess_symbol(q)
        plan = await plan_v3(PlanRequest(symbol=sym, mode="structure"))
        msg = (plan.get("message_html") if isinstance(plan, dict) else None) or "<i>Plan unavailable</i>"
        return {
            "ok": True,
            "message_html": msg,
            "raw": {
                "mode": "fallback_plan_only",
                "error": f"dexter_error:{e.__class__.__name__}:{str(e) or repr(e)}",
                "symbol": sym,
                "plan": plan,
            },
        }



@router.post("/chat")
async def dexter_chat(req: dict):
    """
    Proxy to Service C /chat (free-form trading chat).
    """
    base = (os.getenv("DEXTER_AGENT_URL") or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="DEXTER_AGENT_URL is not set")

    try:
        async with httpx.AsyncClient(timeout=50.0) as client:
            r = await client.post(f"{base}/chat", json=req)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))
