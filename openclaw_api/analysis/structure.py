from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Candle:
    ts: int
    o: float
    h: float
    l: float
    c: float
    v: float


@dataclass(frozen=True)
class Pivot:
    idx: int
    ts: int
    price: float
    kind: str  # "H" or "L"


@dataclass(frozen=True)
class Swings:
    swing_high: Optional[Pivot]
    swing_low: Optional[Pivot]


def detect_pivots(candles: List[Candle], left: int = 3, right: int = 3) -> List[Pivot]:
    pivots: List[Pivot] = []
    n = len(candles)
    if n < left + right + 5:
        return pivots

    for i in range(left, n - right):
        hi = candles[i].h
        lo = candles[i].l

        is_ph = True
        is_pl = True

        # left window
        for j in range(i - left, i):
            if candles[j].h >= hi:
                is_ph = False
            if candles[j].l <= lo:
                is_pl = False
            if not is_ph and not is_pl:
                break

        if is_ph:
            # right window
            for j in range(i + 1, i + right + 1):
                if candles[j].h >= hi:
                    is_ph = False
                    break

        if is_pl:
            for j in range(i + 1, i + right + 1):
                if candles[j].l <= lo:
                    is_pl = False
                    break

        if is_ph:
            pivots.append(Pivot(i, candles[i].ts, hi, "H"))
        if is_pl:
            pivots.append(Pivot(i, candles[i].ts, lo, "L"))

    return pivots


def last_swings(pivots: List[Pivot]) -> Swings:
    sh = None
    sl = None
    for p in reversed(pivots):
        if sh is None and p.kind == "H":
            sh = p
        if sl is None and p.kind == "L":
            sl = p
        if sh and sl:
            break
    return Swings(swing_high=sh, swing_low=sl)


def bos_choch_note(last_close: float, swings: Swings, bias: str) -> str:
    sh = swings.swing_high.price if swings.swing_high else None
    sl = swings.swing_low.price if swings.swing_low else None

    if sh is None or sl is None:
        return "Structure: insufficient pivots"

    # BOS definition: close beyond swing in bias direction
    if bias == "BULLISH" and last_close > sh:
        return "Bullish BOS: close > swing_high"
    if bias == "BEARISH" and last_close < sl:
        return "Bearish BOS: close < swing_low"

    # CHOCH: first break against bias
    if bias == "BULLISH" and last_close < sl:
        return "CHOCH: bullish bias but close < swing_low"
    if bias == "BEARISH" and last_close > sh:
        return "CHOCH: bearish bias but close > swing_high"

    return "Structure: within swings"
