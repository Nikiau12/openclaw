from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
import httpx


router = APIRouter(prefix="/market", tags=["market"])

MEXC_BASE = "https://api.mexc.com"


def _is_stable_pair(sym: str, quote: str) -> bool:
    s = sym.upper()
    q = quote.upper()
    # treat stable/stable as noise in top lists
    stables = {"USDT","USDC","BUSD","TUSD","DAI","FDUSD","USDP"}
    for st in stables:
        if s == f"{st}{q}" or s == f"{q}{st}":
            return True
    return False


def _is_trash_symbol(sym: str) -> bool:
    s = sym.upper()
    # common leveraged token patterns
    if s.endswith("3L") or s.endswith("3S") or s.endswith("5L") or s.endswith("5S"):
        return True
    if "BULL" in s or "BEAR" in s:
        return True
    if "UP" in s and s.endswith("USDT"):  # rough, but ok for now
        # avoid false positives like "JUPUSDT"? We'll keep this conservative:
        # only treat as trash if it contains "UP" AND also ends with "USDT" AND length suggests token suffix.
        pass
    return False


@router.get("/top")
async def market_top(
    quote: str = Query("USDT", min_length=2, max_length=10),
    limit: int = Query(10, ge=1, le=100),
    min_quote_volume_24h: float = Query(0.0, ge=0.0),,
    exclude_stables: bool = Query(True),
    exclude_wrapped: bool = Query(True),
    exclude_patterns: str | None = Query(None)

):
    """
    Top symbols by 24h quoteVolume (spot), filtered by quote currency (default USDT).
    """
    try:
        q = quote.upper().strip()

        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(f"{MEXC_BASE}/api/v3/ticker/24hr")
            r.raise_for_status()
            tickers = r.json()

        if not isinstance(tickers, list):
            raise HTTPException(status_code=502, detail="Unexpected MEXC response")

        out = []
        suffix = q  # e.g. USDT
        patterns = []
        if exclude_patterns:
            patterns = [p.strip().upper() for p in exclude_patterns.split(",") if p.strip()]
        for t in tickers:
            sym = str(t.get("symbol", "")).upper()
            if not sym.endswith(suffix):
            if exclude_wrapped and ("(" in sym or ")" in sym):
                continue
            if exclude_stables and _is_stable_pair(sym, suffix):
                continue
            if patterns and any(pat in sym for pat in patterns):
                continue
                continue
            if _is_trash_symbol(sym):
                continue

            qv = t.get("quoteVolume")
            if qv is None:
                continue
            try:
                qv_f = float(qv)
            except Exception:
                continue

            if qv_f < float(min_quote_volume_24h):
                continue

            # keep compact response
            out.append({
                "symbol": sym,
                "last": float(t.get("lastPrice") or 0.0),
                "change_pct_24h": float(t.get("priceChangePercent") or 0.0) * 100.0,  # ratio -> %
                "quote_volume_24h": qv_f,
                "high_24h": float(t.get("highPrice") or 0.0),
                "low_24h": float(t.get("lowPrice") or 0.0),
            })

        out.sort(key=lambda x: x["quote_volume_24h"], reverse=True)
        return {"ok": True, "quote": q, "limit": limit, "items": out[:limit]}

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"MEXC error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
