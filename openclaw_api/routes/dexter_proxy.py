from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

router = APIRouter(prefix="/dexter", tags=["dexter"])


class DexterRunRequest(BaseModel):
    query: str


def _base() -> str:
    return (os.getenv("DEXTER_AGENT_URL") or "").strip().rstrip("/")


@router.get("/health")
async def dexter_health():
    base = _base()
    if not base:
        raise HTTPException(status_code=503, detail="DEXTER_AGENT_URL not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base}/health")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/run")
async def dexter_run(req: DexterRunRequest):
    base = _base()
    if not base:
        raise HTTPException(status_code=503, detail="DEXTER_AGENT_URL not configured")

    q = (req.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query is empty")

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(f"{base}/run", json={"query": q})
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Dexter error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
