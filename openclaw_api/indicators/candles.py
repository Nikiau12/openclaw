from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass(frozen=True)
class Candles:
    ts: list[int]        # open time (ms)
    o: list[float]
    h: list[float]
    l: list[float]
    c: list[float]
    v: list[float]
    close_ts: list[int]  # close time (ms)


def parse_mexc_klines(raw: list[list]) -> Candles:
    # Format (Binance-like):
    # [ openTime, open, high, low, close, volume, closeTime, ... ]
    ts, o, h, l, c, v, close_ts = [], [], [], [], [], [], []
    for row in raw:
        ts.append(int(row[0]))
        o.append(float(row[1]))
        h.append(float(row[2]))
        l.append(float(row[3]))
        c.append(float(row[4]))
        v.append(float(row[5]))
        close_ts.append(int(row[6]))
    return Candles(ts=ts, o=o, h=h, l=l, c=c, v=v, close_ts=close_ts)


def drop_unclosed_tail(c: Candles) -> Candles:
    # no-repaint: drop last candle if not closed yet
    if not c.close_ts:
        return c
    now_ms = int(time() * 1000)
    if now_ms < c.close_ts[-1]:
        return Candles(
            ts=c.ts[:-1],
            o=c.o[:-1],
            h=c.h[:-1],
            l=c.l[:-1],
            c=c.c[:-1],
            v=c.v[:-1],
            close_ts=c.close_ts[:-1],
        )
    return c
