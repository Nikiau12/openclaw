from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from openclaw_api.exchanges.registry import get_mexc_spot
from openclaw_api.indicators.candles import parse_mexc_klines, drop_unclosed_tail
from openclaw_api.indicators.ema import ema
from openclaw_api.indicators.rsi import rsi
from openclaw_api.indicators.atr import atr


router = APIRouter(prefix="/signals", tags=["signals"])


class BiasRequest(BaseModel):
    symbol: str
    # старшие ТФ по умолчанию
    timeframes: list[str] = ["1h", "4h", "1d"]
    limit: int = 300


def tf_weight(tf: str) -> int:
    # старшие важнее
    return {"1d": 3, "4h": 2, "1h": 1}.get(tf, 1)


@router.post("/bias/v1")
async def bias_v1(req: BiasRequest):
    try:
        p = get_mexc_spot()
        sym = await p.resolve_symbol(req.symbol)

        per_tf = []
        score_total = 0
        weight_total = 0

        for tf in req.timeframes:
            raw = await p.klines(sym, interval=tf, limit=req.limit)
            c = drop_unclosed_tail(parse_mexc_klines(raw))
            closes = c.c

            e_fast = ema(closes, 9)
            e_slow = ema(closes, 21)
            r = rsi(closes, 14)
            a = atr(c.h, c.l, closes, 14)

            i = len(closes) - 1
            if i < 0 or e_fast[i] is None or e_slow[i] is None or r[i] is None or a[i] is None:
                per_tf.append({"tf": tf, "ok": False})
                continue

            ef = float(e_fast[i])
            es = float(e_slow[i])
            rv = float(r[i])
            av = float(a[i])
            last = float(closes[i])

            # TF score:
            #  - EMA cross direction (главное)
            #  - RSI filter (подтверждение/ослабление)
            s = 0
            if ef > es:
                s += 1
            elif ef < es:
                s -= 1

            # RSI gates (не делаем “перекуп/перепрод” как разворот, только фильтр)
            if rv >= 55:
                s += 1
            elif rv <= 45:
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
                "rsi14": rv,
                "atr14": av,
                "score": s,
                "weight": w,
            })

        # aggregate
        if weight_total == 0:
            raise HTTPException(status_code=502, detail="No valid timeframes")

        # thresholds: нужно не просто “плюс один”, а устойчивое большинство
        # max abs score = 2 * weight_total
        if score_total >= weight_total:         # уверенно bullish
            bias = "BULLISH"
        elif score_total <= -weight_total:      # уверенно bearish
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
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
