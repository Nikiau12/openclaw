from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from openclaw_api.indicators.candles import parse_mexc_klines, drop_unclosed_tail
from openclaw_api.indicators.ema import ema
from openclaw_api.indicators.rsi import rsi
from openclaw_api.indicators.atr import atr


router = APIRouter(prefix="/signals", tags=["signals"])

MEXC_BASE = "https://api.mexc.com"


def normalize_symbol(raw: str) -> str:
    # BTC_USDT / btc-usdt / btc/usdt / BTCUSDT -> BTCUSDT
    return raw.strip().upper().replace("/", "").replace("-", "").replace("_", "")


def normalize_interval(tf: str) -> str:
    # MEXC spot supported: 1m,5m,15m,30m,60m,4h,1d,1W,1M
    x = tf.strip().lower()
    if x == "1h":
        return "60m"
    if x == "4h":
        return "4h"
    if x == "1d":
        return "1d"
    if x in {"1w", "1week"}:
        return "1W"
    if x in {"1mo", "1month"}:
        return "1M"
    if x in {"1m", "5m", "15m", "30m", "60m"}:
        return x
    if tf in {"1W", "1M"}:
        return tf
    raise ValueError(f"Unsupported timeframe: {tf}")


def tf_weight(tf: str) -> int:
    # старшие рулит: 1D > 4H > 1H
    return {"1d": 3, "4h": 2, "1h": 1}.get(tf.strip().lower(), 1)


class BiasRequest(BaseModel):
    symbol: str
    timeframes: list[str] = ["1h", "4h", "1d"]
    limit: int = 300


@router.post("/bias/v1")
async def bias_v1(req: BiasRequest):
    try:
        sym = normalize_symbol(req.symbol)

        per_tf = []
        score_total = 0
        weight_total = 0

        async with httpx.AsyncClient(timeout=12.0) as client:
            for tf in req.timeframes:
                iv = normalize_interval(tf)
                r = await client.get(
                    f"{MEXC_BASE}/api/v3/klines",
                    params={"symbol": sym, "interval": iv, "limit": req.limit},
                )
                r.raise_for_status()
                raw = r.json()

                c = drop_unclosed_tail(parse_mexc_klines(raw))
                closes = c.c
                if not closes:
                    per_tf.append({"tf": tf, "ok": False})
                    continue

                e_fast = ema(closes, 9)
                e_slow = ema(closes, 21)
                rv = rsi(closes, 14)
                av = atr(c.h, c.l, closes, 14)

                i = len(closes) - 1
                if e_fast[i] is None or e_slow[i] is None or rv[i] is None or av[i] is None:
                    per_tf.append({"tf": tf, "ok": False})
                    continue

                ef = float(e_fast[i])
                es = float(e_slow[i])
                rsi_v = float(rv[i])
                atr_v = float(av[i])
                last = float(closes[i])

                s = 0
                # EMA direction
                if ef > es:
                    s += 1
                elif ef < es:
                    s -= 1

                # RSI confirmation (filter, not reversal)
                if rsi_v >= 55:
                    s += 1
                elif rsi_v <= 45:
                    s -= 1

                w = tf_weight(tf)
                score_total += s * w
                weight_total += w

                per_tf.append({
                    "tf": tf,
                    "ok": True,
                    "last": last,
                    "ema9": ef,
                    "ema21": es,
                    "rsi14": rsi_v,
                    "atr14": atr_v,
                    "score": s,
                    "weight": w,
                })

        if weight_total == 0:
            bias = "NEUTRAL"
        else:
            # устойчивое большинство
            if score_total >= weight_total:
                bias = "BULLISH"
            elif score_total <= -weight_total:
                bias = "BEARISH"
            else:
                bias = "NEUTRAL"

        return {
            "symbol_raw": req.symbol,
            "symbol": sym,
            "bias": bias,
            "score_total": score_total,
            "weight_total": weight_total,
            "per_tf": per_tf,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"MEXC error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
