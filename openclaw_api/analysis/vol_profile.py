from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .structure import Candle


@dataclass(frozen=True)
class VP:
    poc: float
    lvn_above: Optional[float]
    lvn_below: Optional[float]


def build_vp(candles: List[Candle], bins: int = 48, use_last_n: int = 200) -> VP:
    data = candles[-use_last_n:] if len(candles) > use_last_n else candles
    if len(data) < 30:
        last = candles[-1].c if candles else 0.0
        return VP(poc=last, lvn_above=None, lvn_below=None)

    tps = [((c.h + c.l + c.c) / 3.0, float(c.v)) for c in data]
    min_p = min(tp for tp, _ in tps)
    max_p = max(tp for tp, _ in tps)
    if max_p <= min_p:
        last = candles[-1].c
        return VP(poc=last, lvn_above=None, lvn_below=None)

    step = (max_p - min_p) / bins
    vols = [0.0] * bins

    for price, vol in tps:
        idx = int((price - min_p) / step)
        if idx >= bins:
            idx = bins - 1
        if idx < 0:
            idx = 0
        vols[idx] += vol

    poc_idx = max(range(bins), key=lambda i: vols[i])
    poc_price = min_p + (poc_idx + 0.5) * step

    # LVN zones: volumes below 20th percentile
    sorted_vols = sorted(vols)
    thr = sorted_vols[max(0, int(0.2 * (len(sorted_vols) - 1)))]
    low_bins = [i for i, v in enumerate(vols) if v <= thr]

    # current price approx: last close in last candle
    last_price = data[-1].c
    cur_idx = int((last_price - min_p) / step)
    cur_idx = max(0, min(bins - 1, cur_idx))

    def bin_price(i: int) -> float:
        return min_p + (i + 0.5) * step

    above = [i for i in low_bins if i > cur_idx]
    below = [i for i in low_bins if i < cur_idx]

    lvn_above = bin_price(min(above)) if above else None
    lvn_below = bin_price(max(below)) if below else None

    return VP(poc=poc_price, lvn_above=lvn_above, lvn_below=lvn_below)
