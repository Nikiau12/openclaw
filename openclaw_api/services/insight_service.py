from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import os

import httpx

from openclaw_api.routes.bias_v1 import (
    compute_bias,
    normalize_symbol,
    normalize_interval,
    MEXC_BASE,
)
from openclaw_api.analysis.structure import Candle, detect_pivots, last_swings, bos_choch_note
from openclaw_api.analysis.vol_profile import build_vp
from openclaw_api.indicators.candles import parse_mexc_klines, drop_unclosed_tail


CRYPTOPANIC_API_TOKEN = os.getenv("CRYPTOPANIC_API_TOKEN", "").strip()
CRYPTOPANIC_BASE = "https://cryptopanic.com/api/v1/posts/"


@dataclass
class NewsItem:
    title: str
    body: str


@dataclass
class InsightResult:
    symbol: str
    verdict: str
    bias: str
    news_sentiment: str
    structure_note: str
    poc: float
    last_price: float
    conflicts: list[str]
    chart_only: bool


async def _fetch_4h_candles(symbol: str, limit: int = 200) -> list[Candle]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        r = await client.get(
            f"{MEXC_BASE}/api/v3/klines",
            params={
                "symbol": symbol,
                "interval": normalize_interval("4h"),
                "limit": limit,
            },
        )
        r.raise_for_status()
        raw = r.json()

    c = drop_unclosed_tail(parse_mexc_klines(raw))
    candles: list[Candle] = []
    for i in range(len(c.c)):
        candles.append(
            Candle(
                ts=int(c.ts[i]),
                o=float(c.o[i]),
                h=float(c.h[i]),
                l=float(c.l[i]),
                c=float(c.c[i]),
                v=float(c.v[i]),
            )
        )
    return candles


async def _analyze_chart(
    symbol: str,
    timeframes: list[str],
    limit: int,
) -> tuple[str, float, str, float]:
    bias_data = await compute_bias(symbol=symbol, timeframes=timeframes, limit=limit)
    bias = str(bias_data.get("bias", "NEUTRAL")).upper()

    per_tf = bias_data.get("per_tf", []) or []
    ok_tfs = [x for x in per_tf if x.get("ok")]

    last_price = 0.0
    for tf_name in ("1h", "4h", "1d"):
        for row in ok_tfs:
            if str(row.get("tf", "")).lower().strip() == tf_name:
                last_price = float(row.get("last", 0.0))
                break
        if last_price:
            break

    structure_note = "Structure: unavailable"
    poc = last_price

    try:
        candles = await _fetch_4h_candles(symbol=symbol, limit=max(100, min(limit, 300)))
        if candles:
            pivots = detect_pivots(candles)
            swings = last_swings(pivots)
            structure_note = bos_choch_note(last_price, swings, bias)

            vp = build_vp(candles)
            poc = float(vp.poc)
    except Exception:
        pass

    return bias, last_price, structure_note, poc


async def _fetch_news(symbol: str, limit: int = 10) -> list[NewsItem]:
    if not CRYPTOPANIC_API_TOKEN:
        return []

    currency = symbol.replace("USDT", "").replace("USD", "").strip().upper()
    if not currency:
        return []

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                CRYPTOPANIC_BASE,
                params={
                    "auth_token": CRYPTOPANIC_API_TOKEN,
                    "currencies": currency,
                    "public": "true",
                },
            )
            r.raise_for_status()
            data = r.json()

        items: list[NewsItem] = []
        for row in (data.get("results") or [])[:limit]:
            items.append(
                NewsItem(
                    title=str(row.get("title") or "").strip(),
                    body=str(row.get("body") or "").strip(),
                )
            )
        return items
    except Exception:
        return []


_BULLISH_WORDS = {
    "bullish", "pump", "surge", "rally", "approval", "approved",
    "etf", "buy", "breakout", "launch", "partnership", "upgrade",
    "adoption", "inflow", "listing",
}
_BEARISH_WORDS = {
    "bearish", "dump", "crash", "ban", "hack", "sell",
    "lawsuit", "liquidation", "drop", "fear", "exploit",
    "outflow", "delay", "delayed", "rejection", "rejected",
}


def _classify_news(items: list[NewsItem]) -> str:
    if not items:
        return "unavailable"

    score = 0
    for item in items:
        text = f"{item.title} {item.body}".lower()
        score += sum(1 for w in _BULLISH_WORDS if w in text)
        score -= sum(1 for w in _BEARISH_WORDS if w in text)

    if score >= 2:
        return "bullish"
    if score <= -2:
        return "bearish"
    return "neutral"


def _aggregate_verdict(bias: str, news_sentiment: str) -> tuple[str, list[str]]:
    conflicts: list[str] = []

    if news_sentiment == "unavailable":
        return (
            {
                "BULLISH": "bullish",
                "BEARISH": "bearish",
                "NEUTRAL": "neutral",
            }.get(bias, "neutral"),
            conflicts,
        )

    if bias == "BULLISH" and news_sentiment == "bearish":
        conflicts.append("Чарт бычий, а новостной фон медвежий")
        return "conflicted", conflicts

    if bias == "BEARISH" and news_sentiment == "bullish":
        conflicts.append("Чарт медвежий, а новостной фон бычий")
        return "conflicted", conflicts

    if bias == "BULLISH":
        return "bullish", conflicts
    if bias == "BEARISH":
        return "bearish", conflicts
    return "neutral", conflicts


async def run_insight(
    symbol: str,
    timeframes: Optional[list[str]] = None,
    limit: int = 300,
) -> InsightResult:
    sym = normalize_symbol(symbol)
    if not sym:
        raise ValueError("empty symbol")

    tfs = timeframes or ["1h", "4h", "1d"]

    chart_task = _analyze_chart(symbol=sym, timeframes=tfs, limit=limit)
    news_task = _fetch_news(symbol=sym)

    (bias, last_price, structure_note, poc), news_items = await __import__("asyncio").gather(
        chart_task,
        news_task,
    )

    news_sentiment = _classify_news(news_items)
    verdict, conflicts = _aggregate_verdict(bias, news_sentiment)

    return InsightResult(
        symbol=sym,
        verdict=verdict,
        bias=bias,
        news_sentiment=news_sentiment,
        structure_note=structure_note,
        poc=float(poc),
        last_price=float(last_price),
        conflicts=conflicts,
        chart_only=(news_sentiment == "unavailable"),
    )
