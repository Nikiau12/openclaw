from __future__ import annotations


def ema(values: list[float], period: int) -> list[float | None]:
    n = len(values)
    if period <= 0 or n == 0:
        return [None] * n

    out: list[float | None] = [None] * n
    if n < period:
        return out

    k = 2.0 / (period + 1.0)

    # seed: SMA of first period
    s = 0.0
    for i in range(period):
        s += values[i]
    prev = s / period
    out[period - 1] = prev

    for i in range(period, n):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev

    return out
