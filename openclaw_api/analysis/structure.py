from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SwingLevels:
    swing_high: Optional[float]
    swing_low: Optional[float]


def _pivots(high: list[float], low: list[float], left: int = 3, right: int = 3):
    n = len(high)
    ph = [False] * n
    pl = [False] * n
    for i in range(left, n - right):
        h = high[i]
        l = low[i]
        if all(h > high[j] for j in range(i - left, i)) and all(h > high[j] for j in range(i + 1, i + right + 1)):
            ph[i] = True
        if all(l < low[j] for j in range(i - left, i)) and all(l < low[j] for j in range(i + 1, i + right + 1)):
            pl[i] = True
    return ph, pl


def swings_from_candles(high: list[float], low: list[float], close: list[float], left: int = 3, right: int = 3) -> SwingLevels:
    if not high or not low or not close:
        return SwingLevels(None, None)

    ph, pl = _pivots(high, low, left=left, right=right)

    last_sh = None
    last_sl = None
    for i in range(len(high) - 1, -1, -1):
        if last_sh is None and ph[i]:
            last_sh = float(high[i])
        if last_sl is None and pl[i]:
            last_sl = float(low[i])
        if last_sh is not None and last_sl is not None:
            break

    return SwingLevels(last_sh, last_sl)
