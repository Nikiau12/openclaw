from __future__ import annotations

from html import escape
from typing import Any, Iterable, List

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from openclaw_api.routes.bias_v1 import (
    compute_bias,
    normalize_symbol,
    normalize_interval,
    MEXC_BASE,
)

from openclaw_api.analysis.structure import Candle, detect_pivots, structure_signal
from openclaw_api.analysis.regime import atr as atr_from_candles, ema, detect_regime
from openclaw_api.analysis.vol_profile import build_volume_profile


router = APIRouter(tags=["plan"])


class PlanV4Request(BaseModel):
    symbol: str
    timeframes: list[str] = ["1h", "4h", "1d"]
    limit: int = 300


def safe(s: str) -> str:
    return escape(s, quote=False)


def fmt_price(x: float) -> str:
    # Same spirit as v3: micro-price friendly
    ax = abs(x)
    if ax == 0:
        return "0"
    if ax >= 1000:
        s = f"{x:,.2f}"
    elif ax >= 1:
        s = f"{x:,.4f}"
    elif ax >= 0.01:
        s = f"{x:.6f}"
    elif ax >= 0.0001:
        s = f"{x:.8f}"
    else:
        s = f"{x:.10f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def to_candles_mexc_klines(rows: Iterable[Iterable[Any]]) -> List[Candle]:
    """
    MEXC spot /api/v3/klines rows are typically:
      [openTime, open, high, low, close, volume, closeTime, quoteAssetVolume, ...]
    We take first 6 fields.
    """
    out: List[Candle] = []
    for r in rows:
        r = list(r)
        out.append(
            Candle(
                ts=int(r[0]),
                o=float(r[1]),
                h=float(r[2]),
                l=float(r[3]),
                c=float(r[4]),
                v=float(r[5]),
            )
        )
    # no repaint: drop last unclosed candle
    return out[:-1] if len(out) > 2 else out


def _tf_label(tf: str) -> str:
    return tf.strip().upper()


@router.post("/plan/v4")
async def plan_v4(req: PlanV4Request):
    try:
        sym = normalize_symbol(req.symbol)

        # 24h summary (same endpoint as v3)
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(f"{MEXC_BASE}/api/v3/ticker/24hr", params={"symbol": sym})
            r.raise_for_status()
            t = r.json()

            last = float(t["lastPrice"])
            change_pct = float(t["priceChangePercent"]) * 100.0  # ratio -> %
            quote_vol = float(t.get("quoteVolume") or 0.0)
            high = float(t["highPrice"])
            low = float(t["lowPrice"])

            # Bias engine (already does no-repaint via drop_unclosed_tail)
            b = await compute_bias(symbol=sym, timeframes=req.timeframes, limit=req.limit)
            bias = b["bias"]
            score_total = int(b["score_total"])
            weight_total = int(b["weight_total"])
            per_tf = b["per_tf"]

            icon = {"BULLISH": "🟩", "BEARISH": "🟥", "NEUTRAL": "🟦"}[bias]

            # --- Multi-TF ATR from bias per_tf (already computed)
            atr_1h = atr_4h = atr_1d = 0.0
            for x in per_tf:
                if not x.get("ok"):
                    continue
                tf = x["tf"].strip().lower()
                av = float(x["atr14"])
                if tf == "1h":
                    atr_1h = av
                elif tf == "4h":
                    atr_4h = av
                elif tf == "1d":
                    atr_1d = av

            # --- Fetch klines for structure/VP/EMA/regime (we need OHLCV candles)
            # Use the same interval normalization as bias_v1
            iv_1h = normalize_interval("1h")
            iv_4h = normalize_interval("4h")
            iv_1d = normalize_interval("1d")

            r1 = await client.get(f"{MEXC_BASE}/api/v3/klines", params={"symbol": sym, "interval": iv_1h, "limit": req.limit})
            r4 = await client.get(f"{MEXC_BASE}/api/v3/klines", params={"symbol": sym, "interval": iv_4h, "limit": req.limit})
            rD = await client.get(f"{MEXC_BASE}/api/v3/klines", params={"symbol": sym, "interval": iv_1d, "limit": req.limit})
            r1.raise_for_status()
            r4.raise_for_status()
            rD.raise_for_status()

            c1 = to_candles_mexc_klines(r1.json())
            c4 = to_candles_mexc_klines(r4.json())
            cD = to_candles_mexc_klines(rD.json())

        if not c1 or not c4 or not cD:
            raise HTTPException(status_code=404, detail="No candle data")

        # --- Regime detection (4H)
        reg = detect_regime(c4)
        buf_mult = 1.2 if reg.kind == "TREND" else 1.8

        # --- Multi-TF ATR reference (prefer computed ones; fallback to candles ATR if zeros)
        atr_ref = max(atr_1h, atr_4h, atr_1d)
        if atr_ref <= 0:
            atr_ref = max(atr_from_candles(c1, 14), atr_from_candles(c4, 14), atr_from_candles(cD, 14))

        buf = atr_ref * buf_mult

        # --- Structure-first (4H pivots)
        piv = detect_pivots(c4, left=2, right=2)
        struct_label, long_lv, short_lv = structure_signal(pivots=piv, bias=bias)

        # --- EMA21 dynamic (1H + 4H)
        e21_1h = ema([x.c for x in c1], 21)[-1]
        e21_4h = ema([x.c for x in c4], 21)[-1]

        # --- Volume Profile (4H)
        vp = build_volume_profile(c4, bins=48, use_last_n=200)

        # --- Levels: structure + ATR buffer
        long_trigger = long_invalidation = None
        short_trigger = short_invalidation = None

        if long_lv:
            long_trigger = long_lv.trigger + buf
            long_invalidation = long_lv.invalidation - buf

        if short_lv:
            short_trigger = short_lv.trigger - buf
            short_invalidation = short_lv.invalidation + buf

        # --- TF line + Drivers (HTML-safe)
        parts = []
        ok_tfs = [x for x in per_tf if x.get("ok")]
        for x in ok_tfs:
            parts.append(f"{_tf_label(x['tf'])}:{int(x['score']):+d}")
        tf_line = ""
        if parts:
            tf_line = f"📊 <b>TF</b>: {' | '.join(parts)} → <code>{score_total}/{weight_total}</code>\n"

        ok_tfs.sort(key=lambda k: int(k.get("weight", 0)), reverse=True)
        reasons = []
        for x in ok_tfs[:2]:
            ef = float(x["ema9"])
            es = float(x["ema21"])
            rv = float(x["rsi14"])
            rel = "&gt;" if ef > es else "&lt;" if ef < es else "="
            reasons.append(f"{_tf_label(x['tf'])} EMA9{rel}EMA21, RSI {rv:.0f}")
        reasons_line = ""
        if reasons:
            reasons_line = f"🧩 <b>Drivers</b>: {' | '.join(reasons)}\n"

        # --- Message (HTML-safe)
        msg = (
            f"📌 <b>{safe(req.symbol)}</b> → <code>{safe(sym)}</code>\n"
            f"{icon} <b>Bias</b>: {safe(bias)}\n"
            f"{tf_line}"
            f"{reasons_line}\n"
            f"💰 <b>Last</b>: <code>{fmt_price(last)}</code>\n"
            f"📈 <b>24h</b>: <code>{change_pct:+.2f}%</code>\n"
            f"🌊 <b>QuoteVol</b>: <code>{quote_vol:,.0f}</code>\n"
            f"⬆️ <b>High</b>: <code>{fmt_price(high)}</code>\n"
            f"⬇️ <b>Low</b>: <code>{fmt_price(low)}</code>\n"
            f"\n🧭 <b>Regime</b>: <b>{safe(reg.kind)}</b> <code>{reg.score:.2f}</code>\n"
            f"📏 <b>ATR max(1H/4H/1D)</b>: <code>{fmt_price(atr_ref)}</code> • buffer x{buf_mult:.1f}\n"
            f"\n🏗️ <b>Structure (4H)</b>: {safe(struct_label)}\n"
            f"⚡ <b>EMA21</b>: 1H <code>{fmt_price(e21_1h)}</code> • 4H <code>{fmt_price(e21_4h)}</code>\n"
            f"\n📦 <b>Volume Profile (4H)</b>\n"
            f"POC: <code>{fmt_price(vp.poc)}</code>\n"
        )

        if vp.hvn:
            msg += "HVN: " + " • ".join(f"<code>{fmt_price(x)}</code>" for x in vp.hvn[:3]) + "\n"
        if vp.lvn:
            msg += "LVN: " + " • ".join(f"<code>{fmt_price(x)}</code>" for x in vp.lvn[:3]) + "\n"

        msg += "\n🎯 <b>Levels</b>\n"
        if long_trigger is not None:
            msg += (
                f"🟩 <b>LONG</b> trigger: <code>{fmt_price(long_trigger)}</code> | invalid: <code>{fmt_price(long_invalidation)}</code>\n"
            )
        if short_trigger is not None:
            msg += (
                f"🟥 <b>SHORT</b> trigger: <code>{fmt_price(short_trigger)}</code> | invalid: <code>{fmt_price(short_invalidation)}</code>\n"
            )

        if reg.kind == "RANGE":
            msg += "\n<i>Range режим: буфер увеличен. Жди подтверждение.</i>\n"

        msg += "\n🚨 <b>Риск-правило</b>: стоп обязателен.\n"

        return {
            "ok": True,
            "message_html": msg,
            "meta": {
                "symbol": sym,
                "bias": bias,
                "regime": reg.kind,
                "atr_ref": atr_ref,
                "buffer_mult": buf_mult,
            },
        }

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"MEXC error: {e.response.status_code}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
