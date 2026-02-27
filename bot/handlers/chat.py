import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from bot.clients.api import get, post, APIError

router = Router()

@router.message(Command("start"))
async def start(m: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/top"), KeyboardButton(text="/scan")],
            [KeyboardButton(text="/plan BTC_USDT")],
            [KeyboardButton(text="📘 Полный гайд")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выбери команду или напиши текст…",
    )

    guide = (
        "<b>OpenClaw — бот для крипто-аналитики</b> (не торговый совет).\n\n"
        "<b>Команды:</b>\n"
        "• <code>/top</code> — топ ликвидных монет\n"
        "• <code>/scan</code> — где сейчас всплеск объёма\n"
        "• <code>/plan BTC_USDT</code> — план по монете (Bias + сценарии)\n\n"
        "Сценарий для новичка:\n"
        "1) <code>/scan</code> → выбери тикер\n"
        "2) <code>/plan TICKER</code> → посмотри Bias и уровни\n"
        "3) Если Bias NEUTRAL → смотри 2 сценария (LONG/SHORT)\n\n"
        "Нужны детали? Нажми <b>📘 Полный гайд</b>."
    )

    await m.answer(guide, parse_mode="HTML", reply_markup=kb)



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




@router.message(F.text == "📘 Полный гайд")
async def full_guide(m: Message):
    guide = (
        "<b>OpenClaw — подробный гайд</b>\n"
        "<i>Это аналитика, не торговый совет.</i>\n\n"

        "<b>Команда /top [N]</b>\n"
        "Показывает топ монет USDT по объёму за 24ч (quoteVolume).\n"
        "Зачем: выбирать ликвидные монеты, где обычно проще вход/выход.\n"
        "Примеры: <code>/top</code>, <code>/top 20</code>\n\n"

        "<b>Команда /scan [tf] [spike] [N]</b>\n"
        "Ищет монеты, где объём последней свечи на выбранном TF резко выше нормы.\n"
        "Spike — это: <b>объём последней свечи</b> / <b>средний объём прошлых свечей</b>.\n"
        "Примеры: <code>/scan</code>, <code>/scan 1h 3 20</code>\n"
        "Как понимать spike:\n"
        "• 2–3×: оживление\n"
        "• 3–5×: сильный импульс\n"
        "• >5×: часто новости/манипуляции — осторожно\n\n"

        "<b>Команда /plan &lt;symbol&gt;</b>\n"
        "Даёт план по монете и контекст рынка на старших TF: 1H/4H/1D.\n"
        "Показывает 24h сводку (цена/изменение/объём), Bias и уровни.\n"
        "Примеры: <code>/plan BTC_USDT</code>, <code>/plan ETHUSDT</code>, <code>/plan sol-usdt</code>\n\n"

        "<b>Как читать Bias</b>\n"
        "Bias бывает: 🟩 BULLISH / 🟥 BEARISH / 🟦 NEUTRAL.\n"
        "Он считается по EMA(9/21) + RSI(14) на закрытых свечах (no repaint),\n"
        "с приоритетом старших TF (1D важнее 4H, 4H важнее 1H).\n\n"

        "<b>📊 TF line</b>\n"
        "Показывает, как “проголосовали” TF:\n"
        "<code>1H:+2 | 4H:+2 | 1D:-2 → 0/6</code>\n"
        "Каждый TF даёт score от -2 до +2:\n"
        "• EMA9>EMA21 даёт +1, EMA9<EMA21 даёт -1\n"
        "• RSI≥55 даёт +1, RSI≤45 даёт -1\n"
        "Дальше суммируется с весами (1D=3, 4H=2, 1H=1).\n\n"

        "<b>🧩 Drivers</b>\n"
        "Коротко объясняет, что сильнее всего влияет на вердикт (обычно дневка).\n\n"

        "<b>Уровни и сценарии</b>\n"
        "Trigger — уровень, после которого сценарий считается активным.\n"
        "Invalidation — уровень, при котором сценарий ломается.\n"
        "Если Bias NEUTRAL, бот даёт 2 сценария: LONG и SHORT.\n\n"

        "<b>Рекомендуемый сценарий использования</b>\n"
        "1) <code>/scan</code> → выбрал тикер\n"
        "2) <code>/plan TICKER</code> → понял Bias и сценарии\n"
        "3) Дальше действуешь по своей стратегии и риск-менеджменту.\n"
    )
    await m.answer(guide, parse_mode="HTML")

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
