from __future__ import annotations

from typing import Any, Dict, List, Optional
import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

from openclaw_api.indicators.candles import parse_mexc_klines, drop_unclosed_tail

# reuse helpers from market_top
from openclaw_api.routes.market_top import (
    MEXC_BASE,
    _is_wrapped_or_synthetic,
    _is_leveraged_or_trash,
    _is_stable_pair,
    _safe_float,
)

router = APIRouter(prefix="/market", tags=["market"])


def normalize_symbol(raw: str) -> str:
    return raw.strip().upper().replace("/", "").replace("-", "").replace("_", "")


def normalize_interval(tf: str) -> str:
    # MEXC spot supported: 1m,5m,15m,30m,60m,4h,1d,1W,1M
    x = tf.strip().lower()
    if x == "1h":
        return "60m"
    if x == "4h":
        return "4h"
    if x == "1d":
        return "1d"
    if x in {"1w", "1week"}:
        return "1W"
    if x in {"1mo", "1month"}:
        return "1M"
    if x in {"1m", "5m", "15m", "30m", "60m"}:
        return x
    if tf in {"1W", "1M"}:
        return tf
    raise ValueError(f"Unsupported timeframe: {tf}")


class VolumeSpikeSpec(BaseModel):
    tf: str = Field("15m", description="kline timeframe: 15m/60m/4h/1d etc")
    lookback: int = Field(20, ge=5, le=200, description="avg window for baseline volumes (prev N bars)")
    multiplier: float = Field(2.0, ge=1.0, le=50.0, description="min spike ratio to include")
    limit: int = Field(60, ge=10, le=500, description="how many klines to fetch")


class MarketScanRequest(BaseModel):
    quote: str = "USDT"
    limit: int = Field(20, ge=1, le=100)

    # initial universe filters (tickers-24h)
    min_quote_volume_24h: float = Field(5_000_000.0, ge=0.0)
    min_abs_change_24h: float = Field(0.0, ge=0.0)
    max_abs_change_24h: float = Field(1000.0, ge=0.0)

    # anti-trash
    exclude_stables: bool = True
    exclude_wrapped: bool = True
    exclude_patterns: Optional[str] = None

    # performance guard: how many symbols go into kline stage
    candidate_pool: int = Field(200, ge=10, le=2000)

    # spike filter (optional)
    volume_spike: Optional[VolumeSpikeSpec] = None


def _abs_change_pct_24h(t: Dict[str, Any]) -> float:
    # MEXC returns ratio in priceChangePercent, convert to %
    return abs(_safe_float(t.get("priceChangePercent")) * 100.0)


async def _fetch_spike_for_symbol(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    symbol: str,
    tf: str,
    lookback: int,
    limit: int,
) -> Optional[Dict[str, Any]]:
    async with sem:
        r = await client.get(
            f"{MEXC_BASE}/api/v3/klines",
            params={"symbol": symbol, "interval": tf, "limit": limit},
        )
        r.raise_for_status()
        raw = r.json()

    if not isinstance(raw, list) or len(raw) < (lookback + 2):
        return None

    c = drop_unclosed_tail(parse_mexc_klines(raw))
    vols = c.v
    if len(vols) < (lookback + 2):
        return None

    last_v = float(vols[-1])
    base_window = vols[-(lookback + 1):-1]  # prev lookback bars
    base_avg = sum(base_window) / float(len(base_window)) if base_window else 0.0
    if base_avg <= 0:
        return None

    spike = last_v / base_avg
    return {"symbol": symbol, "spike": spike, "last_vol": last_v, "base_avg": base_avg}


@router.post("/scan")
async def market_scan(req: MarketScanRequest) -> Dict[str, Any]:
    try:
        q = req.quote.upper().strip()
        suffix = q
        patterns: List[str] = []
        if req.exclude_patterns:
            patterns = [p.strip().upper() for p in req.exclude_patterns.split(",") if p.strip()]

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{MEXC_BASE}/api/v3/ticker/24hr")
            r.raise_for_status()
            tickers = r.json()

            if not isinstance(tickers, list):
                raise HTTPException(status_code=502, detail="Unexpected MEXC response (not a list)")

            # stage 1: universe from tickers
            universe: List[Dict[str, Any]] = []
            for t in tickers:
                sym = str(t.get("symbol", "")).upper()
                if not sym or not sym.endswith(suffix):
                    continue

                if req.exclude_wrapped and _is_wrapped_or_synthetic(sym):
                    continue
                if _is_leveraged_or_trash(sym):
                    continue
                if req.exclude_stables and _is_stable_pair(sym, suffix):
                    continue
                if patterns and any(pat in sym for pat in patterns):
                    continue

                qv = _safe_float(t.get("quoteVolume"), default=-1.0)
                if qv < req.min_quote_volume_24h:
                    continue

                abs_ch = _abs_change_pct_24h(t)
                if abs_ch < req.min_abs_change_24h:
                    continue
                if abs_ch > req.max_abs_change_24h:
                    continue

                universe.append({
                    "symbol": sym,
                    "last": _safe_float(t.get("lastPrice")),
                    "change_pct_24h": _safe_float(t.get("priceChangePercent")) * 100.0,
                    "quote_volume_24h": qv,
                    "high_24h": _safe_float(t.get("highPrice")),
                    "low_24h": _safe_float(t.get("lowPrice")),
                })

            # rank by liquidity/volume and cut pool
            universe.sort(key=lambda x: x["quote_volume_24h"], reverse=True)
            pool = universe[: req.candidate_pool]

            # stage 2: optional volume spike
            if req.volume_spike is None:
                return {"ok": True, "mode": "tickers_only", "count": len(pool), "items": pool[: req.limit]}

            tf = normalize_interval(req.volume_spike.tf)
            lookback = int(req.volume_spike.lookback)
            kline_limit = int(req.volume_spike.limit)
            mult = float(req.volume_spike.multiplier)

            sem = asyncio.Semaphore(8)  # concurrency guard
            tasks = [
                _fetch_spike_for_symbol(client, sem, x["symbol"], tf, lookback, kline_limit)
                for x in pool
            ]

            spikes_raw = await asyncio.gather(*tasks, return_exceptions=True)

        # merge results outside client context
        spike_map: Dict[str, Dict[str, Any]] = {}
        for res in spikes_raw:
            if res is None:
                continue
            if isinstance(res, Exception):
                continue
            spike_map[res["symbol"]] = res

        items: List[Dict[str, Any]] = []
        for x in pool:
            s = x["symbol"]
            if s not in spike_map:
                continue
            sp = float(spike_map[s]["spike"])
            if sp < mult:
                continue
            items.append({
                **x,
                "volume_spike": sp,
                "last_vol": float(spike_map[s]["last_vol"]),
                "base_vol_avg": float(spike_map[s]["base_avg"]),
                "tf": req.volume_spike.tf,
                "lookback": lookback,
            })

        # ranking: spike first, then quote volume
        items.sort(key=lambda z: (z["volume_spike"], z["quote_volume_24h"]), reverse=True)

        return {
            "ok": True,
            "mode": "volume_spike",
            "tf": req.volume_spike.tf,
            "lookback": lookback,
            "multiplier": mult,
            "candidate_pool": req.candidate_pool,
            "count": len(items),
            "items": items[: req.limit],
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"MEXC error: {e.response.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
