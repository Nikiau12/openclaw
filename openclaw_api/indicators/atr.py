from __future__ import annotations


def atr(high: list[float], low: list[float], close: list[float], period: int = 14) -> list[float | None]:
    n = len(close)
    out: list[float | None] = [None] * n
    if n <= period:
        return out

    tr: list[float] = [0.0] * n
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        a = high[i] - low[i]
        b = abs(high[i] - close[i - 1])
        c = abs(low[i] - close[i - 1])
        tr[i] = max(a, b, c)

    # seed: SMA of TR
    s = 0.0
    for i in range(1, period + 1):
        s += tr[i]
    prev = s / period
    out[period] = prev

    for i in range(period + 1, n):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev

    return out
