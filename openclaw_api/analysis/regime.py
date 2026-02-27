from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .structure import Candle


@dataclass(frozen=True)
class Regime:
    kind: str  # "TREND" or "RANGE"
    score: float


def ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for x in values[1:]:
        out.append(out[-1] * (1 - k) + x * k)
    return out


def atr(candles: List[Candle], period: int = 14) -> float:
    if len(candles) < period + 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        hi = candles[i].h
        lo = candles[i].l
        pc = candles[i - 1].c
        tr = max(hi - lo, abs(hi - pc), abs(lo - pc))
        trs.append(tr)
    window = trs[-period:]
    return sum(window) / max(1, len(window))


def detect_regime(candles: List[Candle]) -> Regime:
    """
    Stateless heuristic:
      - TREND if EMA21 slope is meaningful vs ATR
      - else RANGE
    """
    if len(candles) < 60:
        return Regime("RANGE", 0.0)

    closes = [c.c for c in candles]
    e21 = ema(closes, 21)

    # slope over last 10 candles
    slope = e21[-1] - e21[-11]
    a = atr(candles, 14)
    if a <= 0:
        return Regime("RANGE", 0.0)

    score = abs(slope) / a
    if score >= 0.6:
        return Regime("TREND", score)
    return Regime("RANGE", score)
