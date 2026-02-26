from __future__ import annotations

from fastapi import APIRouter, HTTPException

from openclaw_api.exchanges.registry import get_mexc_spot


router = APIRouter(prefix="/mexc", tags=["mexc-spot"])


@router.get("/symbols")
async def mexc_symbols():
    try:
        p = get_mexc_spot()
        return await p.symbols_raw()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/resolve")
async def mexc_resolve(raw: str):
    try:
        p = get_mexc_spot()
        symbol = await p.resolve_symbol(raw)
        return {"raw": raw, "symbol": symbol}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/summary")
async def mexc_summary(symbol: str):
    try:
        p = get_mexc_spot()
        resolved = await p.resolve_symbol(symbol)
        return await p.summary_24h(resolved)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
