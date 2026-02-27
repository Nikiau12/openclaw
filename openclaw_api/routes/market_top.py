from __future__ import annotations

from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
import httpx


router = APIRouter(prefix="/market", tags=["market"])

MEXC_BASE = "https://api.mexc.com"


STABLES = {"USDT", "USDC", "BUSD", "TUSD", "DAI", "FDUSD", "USDP", "USD1"}


def _is_wrapped_or_synthetic(sym: str) -> bool:
    # MEXC has symbols like GOLD(XAUT)USDT
    return ("(" in sym) or (")" in sym)


def _is_leveraged_or_trash(sym: str) -> bool:
    s = sym.upper()
    # common leveraged token suffixes
    if s.endswith(("3L", "3S", "5L", "5S")):
        return True
    if "BULL" in s or "BEAR" in s:
        return True
    return False


def _is_stable_pair(sym: str, quote: str) -> bool:
    # stable/stable like USDCUSDT
    s = sym.upper()
    q = quote.upper()
    for st in STABLES:
        if s == f"{st}{q}" or s == f"{q}{st}":
            return True
    return False


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


@router.get("/top")
async def market_top(
    quote: str = Query("USDT", min_length=2, max_length=10),
    limit: int = Query(10, ge=1, le=100),
    min_quote_volume_24h: float = Query(0.0, ge=0.0),
    exclude_stables: bool = Query(True),
    exclude_wrapped: bool = Query(True),
    exclude_patterns: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Top symbols by 24h quoteVolume (spot), filtered by quote currency (default USDT).
    """
    try:
        q = quote.upper().strip()
        patterns: List[str] = []
        if exclude_patterns:
            patterns = [p.strip().upper() for p in exclude_patterns.split(",") if p.strip()]

        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(f"{MEXC_BASE}/api/v3/ticker/24hr")
            r.raise_for_status()
            tickers = r.json()

        if not isinstance(tickers, list):
            raise HTTPException(status_code=502, detail="Unexpected MEXC response (not a list)")

        items: List[Dict[str, Any]] = []
        suffix = q  # e.g. USDT

        for t in tickers:
            sym = str(t.get("symbol", "")).upper()
            if not sym or not sym.endswith(suffix):
                continue

            if exclude_wrapped and _is_wrapped_or_synthetic(sym):
                continue

            if _is_leveraged_or_trash(sym):
                continue

            if exclude_stables and _is_stable_pair(sym, suffix):
                continue

            if patterns:
                hit = False
                for pat in patterns:
                    if pat in sym:
                        hit = True
                        break
                if hit:
                    continue

            qv = _safe_float(t.get("quoteVolume"), default=-1.0)
            if qv < 0:
                continue
            if qv < float(min_quote_volume_24h):
                continue

            items.append({
                "symbol": sym,
                "last": _safe_float(t.get("lastPrice")),
                "change_pct_24h": _safe_float(t.get("priceChangePercent")) * 100.0,  # ratio -> %
                "quote_volume_24h": qv,
                "high_24h": _safe_float(t.get("highPrice")),
                "low_24h": _safe_float(t.get("lowPrice")),
            })

        items.sort(key=lambda x: x["quote_volume_24h"], reverse=True)

        return {"ok": True, "quote": q, "limit": limit, "items": items[:limit]}

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"MEXC error: {e.response.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
