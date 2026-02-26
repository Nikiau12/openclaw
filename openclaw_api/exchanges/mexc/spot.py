from __future__ import annotations

from typing import Any, Sequence

import httpx

from openclaw_api.exchanges.base import SpotProvider, Symbol


class MexcSpot(SpotProvider):
    venue = "mexc"
    _BASE = "https://api.mexc.com"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        # Шаг 2: заменим на shared client из FastAPI lifespan.
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        r = await self._client.get(f"{self._BASE}{path}", params=params)
        r.raise_for_status()
        return r.json()

    async def symbols_raw(self) -> dict:
        return await self._get("/api/v3/exchangeInfo")

    async def list_symbols(self) -> Sequence[Symbol]:
        data = await self.symbols_raw()
        out: list[Symbol] = []
        for s in data.get("symbols", []):
            status = (s.get("status") or "").upper()
            out.append(
                Symbol(
                    symbol=s.get("symbol"),
                    base=s.get("baseAsset"),
                    quote=s.get("quoteAsset"),
                    active=status in {"ENABLED", "TRADING", "1"},
                )
            )
        return out

    async def resolve_symbol(self, raw: str) -> str:
        raw_u = raw.strip().upper().replace("/", "").replace("-", "").replace("_", "").replace("_", "")
        symbols = await self.list_symbols()

        for s in symbols:
            if s.symbol == raw_u:
                return s.symbol

        if not raw_u.endswith("USDT"):
            candidate = f"{raw_u}USDT"
            for s in symbols:
                if s.symbol == candidate:
                    return s.symbol

        raise ValueError(f"Unknown symbol: {raw}")

    async def summary_24h(self, symbol: str) -> dict:
        return await self._get("/api/v3/ticker/24hr", params={"symbol": symbol})
    def _normalize_interval(self, interval: str) -> str:
        """
        MEXC Spot supported intervals (docs):
        1m, 5m, 15m, 30m, 60m, 4h, 1d, 1W, 1M
        We accept friendly aliases like: 1h -> 60m.
        """
        x = interval.strip()

        # normalize case
        xl = x.lower()

        # friendly aliases -> mexc
        if xl == "1h":
            return "60m"
        if xl == "1d":
            return "1d"
        if xl == "4h":
            return "4h"
        if xl in {"1w", "1week"}:
            return "1W"
        if xl in {"1m", "5m", "15m", "30m", "60m"}:
            return xl
        if xl in {"1mo", "1month"}:
            return "1M"
        if x in {"1W", "1M"}:  # already correct
            return x

        raise ValueError(f"Unsupported interval for MEXC spot: {interval}")

    async def klines(self, symbol: str, interval: str, limit: int = 300) -> list[list]:
        # MEXC: /api/v3/klines
        iv = self._normalize_interval(interval)
        return await self._get("/api/v3/klines", params={"symbol": symbol, "interval": iv, "limit": limit})
