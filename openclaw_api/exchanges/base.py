from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, Literal


MarketType = Literal["spot", "futures"]


@dataclass(frozen=True)
class Symbol:
    symbol: str
    base: str | None = None
    quote: str | None = None
    active: bool = True


class SpotProvider(Protocol):
    venue: str

    async def list_symbols(self) -> Sequence[Symbol]:
        ...

    async def resolve_symbol(self, raw: str) -> str:
        ...

    async def summary_24h(self, symbol: str) -> dict:
        ...

    async def symbols_raw(self) -> dict:
        ...
