from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from openclaw_api.exchanges.registry import get_mexc_spot
from openclaw_api.indicators.candles import parse_mexc_klines, drop_unclosed_tail
from openclaw_api.indicators.atr import atr


router = APIRouter(tags=["plan"])


class PlanRequest(BaseModel):
    symbol: str
    timeframes: list[str] = ["1h", "4h", "1d"]
    limit: int = 300


def tf_weight(tf: str) -> int:
    return {"1d": 3, "4h": 2, "1h": 1}.get(tf, 1)


@router.post("/plan/v3")
async def plan_v3(req: PlanRequest):
    try:
        p = get_mexc_spot()
        sym = await p.resolve_symbol(req.symbol)

        # 24h summary (как раньше)
        t = await p.summary_24h(sym)
        last = float(t["lastPrice"])
        change_pct = float(t["priceChangePercent"]) * 100.0
        quote_vol = float(t.get("quoteVolume") or 0.0)
        high = float(t["highPrice"])
        low = float(t["lowPrice"])

        # bias from /signals/bias/v1 logic inline (без сетевого вызова)
        score_total = 0
        weight_total = 0
        atr_ref = None

        for tf in req.timeframes:
            raw = await p.klines(sym, interval=tf, limit=req.limit)
            c = drop_unclosed_tail(parse_mexc_klines(raw))
            a = atr(c.h, c.l, c.c, 14)
            i = len(c.c) - 1
            if i < 0 or a[i] is None:
                continue
            w = tf_weight(tf)
            weight_total += w
            # В plan/v3 берём ATR самого старшего доступного TF как референс
            if tf == "1d":
                atr_ref = float(a[i])
            elif atr_ref is None and tf == "4h":
                atr_ref = float(a[i])
            elif atr_ref is None:
                atr_ref = float(a[i])

        # bias получаем через готовый endpoint? нет, в plan важен только итог:
        # (чтобы не дублировать весь расчёт — bias можно дергать отдельно в UI бота позже)
        # Пока используем упрощение: если change_24h > 0.5 => bullish, < -0.5 => bearish, иначе neutral
        # Реальный bias будет читаться из /signals/bias/v1 ботом на следующем шаге.
        # (Сейчас оставим совместимость и не увеличим latency планом.)
        if change_pct > 0.5:
            bias = "BULLISH"
            icon = "🟩"
        elif change_pct < -0.5:
            bias = "BEARISH"
            icon = "🟥"
        else:
            bias = "NEUTRAL"
            icon = "🟦"

        # уровни на базе ATR старшего TF
        if atr_ref is not None:
            # conservative: trigger = last + 0.5*ATR (bullish) / last - 0.5*ATR (bearish)
            # invalidation = last - 1.5*ATR / last + 1.5*ATR
            if bias == "BULLISH":
                trigger = last + 0.5 * atr_ref
                invalidation = last - 1.5 * atr_ref
            elif bias == "BEARISH":
                trigger = last - 0.5 * atr_ref
                invalidation = last + 1.5 * atr_ref
            else:
                trigger = None
                invalidation = None
        else:
            trigger = None
            invalidation = None

        msg = (
            f"📌 <b>{req.symbol}</b> → <code>{sym}</code>\n"
            f"{icon} <b>Bias</b>: {bias}\n\n"
            f"💰 <b>Last</b>: <code>{last:.2f}</code>\n"
            f"📈 <b>24h</b>: <code>{change_pct:+.2f}%</code>\n"
            f"🌊 <b>QuoteVol</b>: <code>{quote_vol:,.0f}</code>\n"
            f"⬆️ <b>High</b>: <code>{high:.2f}</code>\n"
            f"⬇️ <b>Low</b>: <code>{low:.2f}</code>\n"
        )

        if trigger is not None and invalidation is not None:
            msg += (
                f"\n🎯 <b>Trigger</b>: <code>{trigger:.2f}</code>\n"
                f"🧯 <b>Invalidation</b>: <code>{invalidation:.2f}</code>\n"
            )

        msg += "\n🚨 <b>Риск-правило</b>: стоп обязателен.\n"

        return {"ok": True, "message_html": msg}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
