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
    async def klines(self, symbol: str, interval: str, limit: int = 300) -> list[list]:
        # MEXC: /api/v3/klines
        return await self._get("/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": limit})
