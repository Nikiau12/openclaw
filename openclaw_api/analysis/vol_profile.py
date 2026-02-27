from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class VolumeProfile:
    poc: Optional[float]
    lvn_above: Optional[float]
    lvn_below: Optional[float]


def build_volume_profile(
    high: list[float],
    low: list[float],
    close: list[float],
    vol: list[float],
    bins: int = 48,
) -> VolumeProfile:
    n = min(len(close), len(vol), len(high), len(low))
    if n < 20:
        return VolumeProfile(None, None, None)

    prices = [ (high[i] + low[i] + close[i]) / 3.0 for i in range(n) ]
    pmin = min(prices)
    pmax = max(prices)
    if pmax <= pmin:
        return VolumeProfile(None, None, None)

    step = (pmax - pmin) / float(bins)
    if step <= 0:
        return VolumeProfile(None, None, None)

    buckets = [0.0] * bins
    for i in range(n):
        idx = int((prices[i] - pmin) / step)
        idx = max(0, min(bins - 1, idx))
        buckets[idx] += float(vol[i])

    poc_i = max(range(bins), key=lambda i: buckets[i])
    poc = pmin + (poc_i + 0.5) * step

    sorted_vols = sorted(buckets)
    thr = sorted_vols[max(0, int(0.2 * (bins - 1)))]
    lvn_idx = [i for i, v in enumerate(buckets) if v <= thr]

    cur = float(close[n - 1])
    cur_i = int((cur - pmin) / step)
    cur_i = max(0, min(bins - 1, cur_i))

    lvn_above = None
    for i in range(cur_i + 1, bins):
        if i in lvn_idx:
            lvn_above = pmin + (i + 0.5) * step
            break

    lvn_below = None
    for i in range(cur_i - 1, -1, -1):
        if i in lvn_idx:
            lvn_below = pmin + (i + 0.5) * step
            break

    return VolumeProfile(float(poc), float(lvn_above) if lvn_above is not None else None, float(lvn_below) if lvn_below is not None else None)
