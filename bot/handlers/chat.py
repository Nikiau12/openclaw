import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from bot.clients.api import get, post, APIError

router = Router()

@router.message(Command("start"))
async def start(m: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/top"), KeyboardButton(text="/scan")],
            [KeyboardButton(text="/plan BTC_USDT"), KeyboardButton(text="/plan ETH_USDT")],
            [KeyboardButton(text="📘 Полный гайд"), KeyboardButton(text="🧪 Примеры")],
            [KeyboardButton(text="❌ Скрыть кнопки")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выбери команду или напиши текст…",
    )

    hello = "Привет 👋 Я <b>OpenClaw</b>. Помогаю быстро читать рынок и находить активность."
    quick = (
        "<b>Быстрый старт</b>\n"
        "1) <code>/scan</code> → где сейчас всплеск объёма\n"
        "2) <code>/plan TICKER</code> → Bias 1H/4H/1D + сценарии\n"
        "3) <code>/top</code> → топ ликвидных монет\n\n"
        "Нужны детали — нажми <b>📘 Полный гайд</b>.\n"
        "Кнопки можно убрать: <b>❌ Скрыть кнопки</b>."
    )

    await m.answer(hello, parse_mode="HTML")
    await m.answer(quick, parse_mode="HTML", reply_markup=kb)



@router.message(Command("plan"))
async def plan(m: Message):
    # /plan <symbol>
    parts = (m.text or "").split(maxsplit=1)

    # If user typed only /plan -> show quick picker
    if len(parts) == 1:
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="/plan BTC_USDT"), KeyboardButton(text="/plan ETH_USDT")],
                [KeyboardButton(text="/plan SOL_USDT")],
                [KeyboardButton(text="✍️ Своя монета")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="Выбери монету или введи команду…",
        )
        msg = (
            "<b>/plan</b> — выбери монету или введи свою.\n\n"
            "Быстрый выбор: BTC / ETH / SOL.\n"
            "Своя монета: нажми <b>✍️ Своя монета</b>."
        )
        await m.answer(msg, parse_mode="HTML", reply_markup=kb)
        return

    symbol = parts[1].strip()
    try:
        data = await post("/plan/v3", {"symbol": symbol, "mode": "structure"})
        # Fallback: if structure mode fails, retry classic
        if not isinstance(data, dict) or not data.get("ok"):
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
        "<b>📘 OpenClaw — полный гайд для новичков</b>\n"
        "<i>Это аналитика, не торговый совет. Решение и риск — на тебе.</i>\n\n"

        "<b>Зачем бот нужен</b>\n"
        "OpenClaw делает 3 вещи:\n"
        "1) показывает, <b>где прямо сейчас пошёл объём</b> (/scan)\n"
        "2) показывает <b>тренд на старших таймфреймах</b> (/plan)\n"
        "3) помогает выбирать <b>ликвидные монеты</b> (/top)\n\n"

        "━━━━━━━━━━━━━━\n"
        "<b>1) /top [N]</b> — топ ликвидности\n"
        "• <b>Что это:</b> список монет USDT по объёму торгов за 24ч.\n"
        "• <b>Зачем:</b> на ликвидных монетах обычно проще войти/выйти.\n"
        "• <b>Как:</b> <code>/top</code> или <code>/top 20</code>\n\n"

        "Как читать строку в /top:\n"
        "• <code>+/- %</code> — изменение цены за 24 часа\n"
        "• <code>last</code> — текущая цена\n"
        "• <code>vol</code> — объём за 24 часа в USDT (чем больше — тем обычно “живее” рынок)\n\n"

        "━━━━━━━━━━━━━━\n"
        "<b>2) /scan [tf] [spike] [N]</b> — поиск всплеска объёма\n"
        "• <b>Что это:</b> бот ищет монеты, где объём последней свечи выше нормы.\n"
        "• <b>Зачем:</b> всплеск объёма часто означает, что “что-то началось”.\n"
        "• <b>Примеры:</b>\n"
        "  <code>/scan</code> (по умолчанию 15m, spike≥2.5, top 10)\n"
        "  <code>/scan 1h 3 20</code> (часовой всплеск ≥3×, показать 20)\n\n"

        "<b>Что значит spike 2.87×</b>\n"
        "Это формула:\n"
        "<code>spike = volume(последняя свеча) / avg(volume прошлых свечей)</code>\n"
        "Пример: <code>3×</code> = объём сейчас примерно в 3 раза выше обычного.\n\n"

        "<b>Как интерпретировать spike</b>\n"
        "• 2–3×: заметное оживление\n"
        "• 3–5×: сильный импульс\n"
        "• >5×: часто новости/манипуляции — осторожно\n\n"

        "<b>Важно:</b> spike не говорит “покупай”. Он говорит “тут активность”.\n"
        "Дальше ты проверяешь контекст через /plan.\n\n"

        "━━━━━━━━━━━━━━\n"
        "<b>3) /plan &lt;symbol&gt;</b> — план по монете\n"
        "• <b>Что это:</b> контекст + тренд 1H/4H/1D + уровни.\n"
        "• <b>Примеры:</b> <code>/plan BTC_USDT</code>, <code>/plan ETH_USDT</code>, <code>/plan sol-usdt</code>\n\n"

        "<b>Что внутри /plan</b>\n"
        "A) <b>24h сводка</b>: Last, 24h%, QuoteVol, High/Low\n"
        "B) <b>Bias</b>: 🟩 BULLISH / 🟥 BEARISH / 🟦 NEUTRAL\n"
        "C) <b>Объяснение</b>: TF line + Drivers\n"
        "D) <b>Уровни</b>: Trigger/Invalidation или 2 сценария (если Neutral)\n\n"

        "<b>Bias простыми словами</b>\n"
        "Bias — это “куда смотрит рынок” на старших ТФ.\n"
        "Он считается по закрытым свечам (без подглядывания в будущее) с EMA/RSI.\n\n"

        "<b>📊 TF line</b> — как голосовали таймфреймы\n"
        "Пример: <code>1H:+2 | 4H:+1 | 1D:-2 → -6/6</code>\n"
        "• +2 = TF поддерживает рост\n"
        "• -2 = TF поддерживает падение\n"
        "• итог показывает, почему вердикт именно такой\n\n"

        "<b>🧩 Drivers</b> — короткая причина\n"
        "Показывает, какие TF сильнее всего влияют на итог.\n\n"

        "<b>Trigger / Invalidation</b>\n"
        "• <b>Trigger</b> — уровень, после которого сценарий считается “активным”.\n"
        "• <b>Invalidation</b> — уровень, где сценарий ломается.\n"
        "Если Bias NEUTRAL, бот даёт <b>две дорожки</b>: LONG и SHORT.\n\n"

        "━━━━━━━━━━━━━━\n"
        "<b>Рекомендуемый сценарий (самый простой)</b>\n"
        "1) <code>/scan</code> → выбрал 1–3 монеты\n"
        "2) <code>/plan TICKER</code> → смотри Bias и уровни\n"
        "3) работай только со стопом (Invalidation — ориентир)\n\n"

        "<b>Если ты совсем новичок</b>\n"
        "Начни с BTC и ETH:\n"
        "<code>/plan BTC_USDT</code>\n"
        "<code>/plan ETH_USDT</code>\n"
        "И только потом переходи к /scan.\n"
    )
    await m.answer(guide, parse_mode="HTML")



@router.message(F.text == "❌ Скрыть кнопки")
async def hide_buttons(m: Message):
    await m.answer("Ок, убрал кнопки. Если нужно вернуть — напиши /start.", reply_markup=ReplyKeyboardRemove())


@router.message(F.text == "🧪 Примеры")
async def examples(m: Message):
    msg = (
        "<b>Примеры команд</b>\n\n"
        "• Найти активность по объёму:\n"
        "<code>/scan</code>\n"
        "<code>/scan 1h 3 20</code>\n\n"
        "• Получить план по монете:\n"
        "<code>/plan BTC_USDT</code>\n"
        "<code>/plan ETH_USDT</code>\n"
        "<code>/plan SOL_USDT</code>\n\n"
        "• Топ ликвидных монет:\n"
        "<code>/top</code>\n"
        "<code>/top 20</code>\n\n"
        "Совет: <code>/scan</code> → выбрал тикер → <code>/plan</code>."
    )
    await m.answer(msg, parse_mode="HTML")


@router.message(F.text == "✍️ Своя монета")
async def plan_custom_hint(m: Message):
    msg = (
        "<b>Своя монета</b>\n"
        "Напиши команду в любом удобном формате:\n"
        "• <code>/plan ADA_USDT</code>\n"
        "• <code>/plan ada-usdt</code>\n"
        "• <code>/plan ada/usdt</code>\n\n"
        "Подсказка: бот сам нормализует символ."
    )
    await m.answer(msg, parse_mode="HTML")

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
