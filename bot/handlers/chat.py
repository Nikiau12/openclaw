import asyncio
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from bot.clients.api import get, post, APIError

router = Router()

@router.message(Command("start"))
async def start(m: Message):
    await m.answer(
        "Привет 👋\n"
        "Пиши вопрос обычным текстом.\n"
        "Команда: /plan BTC_USDT — получить план.\n",
        parse_mode="HTML"
    )

@router.message(Command("plan"))
async def plan(m: Message):
    parts = (m.text or "").split(maxsplit=1)
    symbol = parts[1].strip() if len(parts) > 1 else "BTC_USDT"
    try:
        data = await post("/plan/v3", {"symbol": symbol})
        msg = data.get("message_html") if isinstance(data, dict) else None
        await m.answer(msg or "⚠️ empty", parse_mode="HTML")
    except APIError as e:
        await m.answer(f"❌ APIError: {e}", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"❌ Error: {type(e).__name__}: {e}", parse_mode="HTML")



@router.message(Command("top"))
async def top(m: Message):
    # /top 10
    try:
        parts = (m.text or "").split()
        limit = 10
        if len(parts) > 1:
            try:
                limit = int(parts[1])
            except Exception:
                limit = 10

        # cap
        if limit < 1:
            limit = 1
        if limit > 20:
            limit = 20

        data = await get("/market/top", params={"quote": "USDT", "limit": limit})
        items = data.get("items", []) if isinstance(data, dict) else []
        if not items:
            await m.answer("⚠️ пусто", parse_mode="HTML")
            return

        lines = [f"🔥 <b>Top {limit} USDT</b> (24h quoteVolume)"]
        for i, it in enumerate(items, start=1):
            sym = it.get("symbol", "?")
            ch = float(it.get("change_pct_24h") or 0.0)
            qv = float(it.get("quote_volume_24h") or 0.0)
            last = float(it.get("last") or 0.0)

            icon = "🟩" if ch > 0 else "🟥" if ch < 0 else "🟦"
            lines.append(
                f"{i}. <code>{sym}</code> {icon} <code>{ch:+.2f}%</code>  "
                f"<code>{last:g}</code>  vol <code>{qv:,.0f}</code>"
            )

        await m.answer("\n".join(lines), parse_mode="HTML")

    except APIError as e:
        await m.answer(f"❌ APIError: {e}", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"❌ Error: {type(e).__name__}: {e}", parse_mode="HTML")


@router.message(Command("scan"))
async def scan(m: Message):
    # /scan [tf] [mult] [limit]
    # examples:
    #   /scan
    #   /scan 1h 3.0
    #   /scan 15m 2.5 20
    try:
        parts = (m.text or "").split()

        tf = "15m"
        mult = 2.5
        limit = 10

        if len(parts) > 1:
            tf = parts[1].strip()
        if len(parts) > 2:
            try:
                mult = float(parts[2])
            except Exception:
                mult = 2.5
        if len(parts) > 3:
            try:
                limit = int(parts[3])
            except Exception:
                limit = 10

        if limit < 1:
            limit = 1
        if limit > 30:
            limit = 30

        payload = {
            "quote": "USDT",
            "limit": limit,
            "candidate_pool": 200,
            "min_quote_volume_24h": 10_000_000,
            "max_abs_change_24h": 40,
            "volume_spike": {
                "tf": tf,
                "lookback": 20,
                "multiplier": mult,
                "limit": 80
            }
        }

        data = await post("/market/scan", payload)
        items = data.get("items", []) if isinstance(data, dict) else []

        if not items:
            await m.answer(f"⚠️ Ничего не нашёл (tf={tf}, spike>={mult}).", parse_mode="HTML")
            return

        # --- trend filter: fetch bias for top N ---
        top_n = min(5, len(items))
        symbols = [items[i].get("symbol", "") for i in range(top_n)]
        symbols = [s for s in symbols if s]

        async def fetch_bias(sym: str):
            # returns (sym, bias, score_total, weight_total) or (sym, None, None, None)
            try:
                b = await post("/signals/bias/v1", {"symbol": sym, "timeframes": ["1h", "4h", "1d"]})
                if not isinstance(b, dict):
                    return (sym, None, None, None)
                return (
                    sym,
                    b.get("bias"),
                    b.get("score_total"),
                    b.get("weight_total"),
                )
            except Exception:
                return (sym, None, None, None)

        bias_results = await asyncio.gather(*[fetch_bias(s) for s in symbols])
        bias_map = {sym: (bias, st, wt) for sym, bias, st, wt in bias_results}

        def bias_icon(b: str | None) -> str:
            return {"BULLISH": "🟩", "BEARISH": "🟥", "NEUTRAL": "🟦"}.get((b or "").upper(), "⚪️")

        lines = [f"🔎 <b>Scan</b> tf=<code>{tf}</code> spike≥<code>{mult:g}</code> (top {limit})"]
        lines.append(f"🧭 Trend filter: bias 1H/4H/1D for top {top_n}")

        for i, it in enumerate(items, start=1):
            sym = it.get("symbol", "?")
            sp = float(it.get("volume_spike") or 0.0)
            ch = float(it.get("change_pct_24h") or 0.0)
            qv = float(it.get("quote_volume_24h") or 0.0)
            last = float(it.get("last") or 0.0)

            icon = "🟩" if ch > 0 else "🟥" if ch < 0 else "🟦"

            b, st, wt = bias_map.get(sym, (None, None, None))
            btxt = ""
            if b:
                try:
                    btxt = f"  {bias_icon(b)} <code>{b}</code> <code>{int(st)}/{int(wt)}</code>"
                except Exception:
                    btxt = f"  {bias_icon(b)} <code>{b}</code>"

            lines.append(
                f"{i}. <code>{sym}</code>  spike <code>{sp:.2f}×</code>{btxt}\n"
                f"    {icon} <code>{ch:+.2f}%</code>  <code>{last:g}</code>  vol <code>{qv:,.0f}</code>"
            )

        await m.answer("\n".join(lines), parse_mode="HTML")

    except APIError as e:
        await m.answer(f"❌ APIError: {e}", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"❌ Error: {type(e).__name__}: {e}", parse_mode="HTML")



@router.message()
async def any_text(m: Message):
    txt = (m.text or "").strip()
    if not txt or txt.startswith("/"):
        return
    try:
        data = await post("/chat", {"text": txt, "user_id": m.from_user.id})
        await m.answer(data.get("answer_html", "⚠️ empty"), parse_mode="HTML")
    except APIError as e:
        await m.answer(f"❌ API: {e}", parse_mode="HTML")
