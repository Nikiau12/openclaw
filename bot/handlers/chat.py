import asyncio
import re
from typing import List, Tuple

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from bot.clients.api import get, post, APIError
from bot.services.access import AccessService
from bot.handlers.pro import LIMIT_REACHED_MESSAGE_RU, pro_keyboard

router = Router()
access_service = AccessService()

# =========================
# Dexter routing (no new command)
# =========================
DEXTER_KEYWORDS = {
    "why", "explain", "dex", "dexter", "research", "analyze", "analysis",
    "почему", "объясни", "объяснение", "разбор", "исследуй", "исследование",
}

def _normalize_symbol(raw: str) -> str:
    s = (raw or "").strip().upper()
    if not s:
        return "BTC_USDT"
    # allow btc-usdt / btc/usdt / btcusdt -> normalize
    s = s.replace("-", "_").replace("/", "_")
    if s.endswith("USDT") and "_" not in s:
        # BTCUSDT -> BTC_USDT
        s = s[:-4] + "_USDT"
    return s

def parse_plan_args(text: str) -> Tuple[str, List[str], str]:
    raw = (text or "").strip()
    raw = re.sub(r"^/plan(@\w+)?\s*", "", raw, flags=re.IGNORECASE).strip()
    if not raw:
        return "BTC_USDT", [], ""
    parts = raw.split()
    symbol = _normalize_symbol(parts[0])

    # robust tokens: strips punctuation so "explain?" still matches
    tokens = [re.sub(r"[^\wа-яё]+", "", p.lower()) for p in parts[1:]]
    tail = " ".join(parts[1:]).strip()
    return symbol, tokens, tail

def should_use_dexter(tokens: List[str], tail: str) -> bool:
    if not tokens and not tail:
        return False
    for t in tokens:
        if t in DEXTER_KEYWORDS:
            return True
    low_tail = (tail or "").lower()
    return any(k in low_tail for k in DEXTER_KEYWORDS)


@router.message(Command("start"))
async def start(m: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/top"), KeyboardButton(text="/scan")],
            [KeyboardButton(text="/plan BTC_USDT"), KeyboardButton(text="/plan ETH_USDT")],
            [KeyboardButton(text="📘 Guide / Полный гайд"), KeyboardButton(text="🧪 Examples / Примеры")],
            [KeyboardButton(text="🧠 Dexter Research")],
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
        "Нужны детали — нажми <b>📘 Guide / Полный гайд</b>.\n"
        "Dexter research: нажми <b>🧠 Dexter Research</b> или напиши <code>/plan BTC_USDT explain</code>.\n"
        "Кнопки можно убрать: <b>❌ Скрыть кнопки</b>."
    )

    await m.answer(hello, parse_mode="HTML")
    await m.answer(quick, parse_mode="HTML", reply_markup=kb)


@router.message(F.text == "🧠 Dexter Research")
async def dexter_menu(m: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧠 BTC_USDT"), KeyboardButton(text="🧠 ETH_USDT")],
            [KeyboardButton(text="🧠 SOL_USDT")],
            [KeyboardButton(text="✍️ Своя монета")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Выбери тикер для Dexter…",
    )
    msg = (
        "<b>🧠 Dexter Research</b>\n\n"
        "Выбери монету ниже — я сделаю research через Dexter.\n\n"
        "Либо напиши текстом:\n"
        "• <code>/plan BTC_USDT explain</code>\n"
        "• <code>/plan BTC_USDT почему</code>\n"
    )
    await m.answer(msg, parse_mode="HTML", reply_markup=kb)


@router.message(F.text == "⬅️ Назад")
async def back_to_start(m: Message):
    await start(m)


@router.message(F.text.startswith("🧠 "))
async def dexter_quick_pick(m: Message):
    user_id = m.from_user.id
    decision = access_service.check(user_id, "plan")
    if not decision.allowed:
        await m.answer(LIMIT_REACHED_MESSAGE_RU, parse_mode="HTML", reply_markup=pro_keyboard())
        return

    raw = (m.text or "").replace("🧠", "").strip()
    symbol = _normalize_symbol(raw)

    # Try Dexter -> fallback to normal plan
    try:
        dex = await post("/dexter/chat", {"query": symbol, "symbol": symbol, "analysis": True})
        if isinstance(dex, dict) and dex.get("ok") and dex.get("message_html"):
            await m.answer(dex["message_html"], parse_mode="HTML", disable_web_page_preview=True)
            access_service.consume(user_id, "plan")
            return
    except APIError:
        pass
    except Exception:
        pass

    # fallback to plan/v3
    try:
        data = await post("/plan/v3", {"symbol": symbol, "mode": "structure"})
        if not isinstance(data, dict) or not data.get("ok"):
            data = await post("/plan/v3", {"symbol": symbol})
        msg = data.get("message_html") if isinstance(data, dict) else None
        await m.answer(msg or "⚠️ empty", parse_mode="HTML", disable_web_page_preview=True)
        access_service.consume(user_id, "plan")
    except APIError as e:
        await m.answer(f"❌ APIError: {e}", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"❌ Error: {type(e).__name__}: {e}", parse_mode="HTML")


@router.message(Command("plan"))
async def plan(m: Message):
    user_id = m.from_user.id
    decision = access_service.check(user_id, "plan")
    if not decision.allowed:
        await m.answer(LIMIT_REACHED_MESSAGE_RU, parse_mode="HTML", reply_markup=pro_keyboard())
        return
    # /plan <symbol> [optional flags/text]
    symbol, tokens, tail = parse_plan_args(m.text or "")

    # If user typed only /plan -> show quick picker
    raw_after_cmd = re.sub(r"^/plan(@\w+)?\s*", "", (m.text or "").strip(), flags=re.IGNORECASE).strip()
    if not raw_after_cmd:
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="/plan BTC_USDT"), KeyboardButton(text="/plan ETH_USDT")],
                [KeyboardButton(text="/plan SOL_USDT")],
                [KeyboardButton(text="✍️ Своя монета")],
                [KeyboardButton(text="🧠 Dexter Research")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="Выбери монету или введи команду…",
        )
        msg = (
            "<b>/plan</b> — выбери монету или введи свою.\n\n"
            "Быстрый выбор: BTC / ETH / SOL.\n"
            "Своя монета: нажми <b>✍️ Своя монета</b>.\n\n"
            "Dexter research: <b>🧠 Dexter Research</b> или <code>/plan BTC_USDT explain</code>."
        )
        await m.answer(msg, parse_mode="HTML", reply_markup=kb)
        return

    use_dex = should_use_dexter(tokens, tail)

    # 1) Dexter path (only sometimes)
    if use_dex:
        try:
            dex = await post("/dexter/chat", {"query": symbol, "symbol": symbol, "analysis": False})
            if isinstance(dex, dict) and dex.get("ok") and dex.get("message_html"):
                await m.answer(dex["message_html"], parse_mode="HTML", disable_web_page_preview=True)
                access_service.consume(user_id, "plan")
                return
        except APIError:
            pass
        except Exception:
            pass

    # 2) Default plan/v3 + fallback classic
    try:
        data = await post("/plan/v3", {"symbol": symbol, "mode": "structure"})
        if not isinstance(data, dict) or not data.get("ok"):
            data = await post("/plan/v3", {"symbol": symbol})
        msg = data.get("message_html") if isinstance(data, dict) else None
        await m.answer(msg or "⚠️ empty", parse_mode="HTML", disable_web_page_preview=True)
    except APIError as e:
        await m.answer(f"❌ APIError: {e}", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"❌ Error: {type(e).__name__}: {e}", parse_mode="HTML")


@router.message(Command("top"))
async def top(m: Message):
    user_id = m.from_user.id
    decision = access_service.check(user_id, "top")
    if not decision.allowed:
        await m.answer(LIMIT_REACHED_MESSAGE_RU, parse_mode="HTML", reply_markup=pro_keyboard())
        return
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
        access_service.consume(user_id, "top")

    except APIError as e:
        await m.answer(f"❌ APIError: {e}", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"❌ Error: {type(e).__name__}: {e}", parse_mode="HTML")


@router.message(Command("scan"))
async def scan(m: Message):
    user_id = m.from_user.id
    decision = access_service.check(user_id, "scan")
    if not decision.allowed:
        await m.answer(LIMIT_REACHED_MESSAGE_RU, parse_mode="HTML", reply_markup=pro_keyboard())
        return

    try:
        parts = (m.text or "").split()
        limit = 11

        if len(parts) > 1:
            try:
                limit = int(parts[1])
            except Exception:
                limit = 11

        if limit < 1:
            limit = 1
        if limit > 15:
            limit = 15

        async def fetch_scan(tf: str, mult: float):
            payload = {
                "quote": "USDT",
                "limit": limit,
                "candidate_pool": 80,
                "min_quote_volume_24h": 5_000_000,
                "max_abs_change_24h": 40,
                "volume_spike": {
                    "tf": tf,
                    "lookback": 20,
                    "multiplier": mult,
                    "limit": 80,
                },
            }
            data = await post("/market/scan", payload)
            if not isinstance(data, dict):
                return []
            return data.get("items", []) or []

        items_15m, items_1h, items_4h = await asyncio.gather(
            fetch_scan("15m", 2.0),
            fetch_scan("1h", 2.0),
            fetch_scan("4h", 1.8),
        )

        buckets = [
            ("15m", items_15m),
            ("1h", items_1h),
            ("4h", items_4h),
        ]

        lines = [
            "🔎 <b>Scan USDT</b>",
            "Активные монеты на <code>15m / 1h / 4h</code>",
            "",
        ]

        total_found = 0

        for tf, items in buckets:
            lines.append(f"<b>{tf}</b>")

            if not items:
                lines.append("• <i>ничего сильного сейчас нет</i>")
                lines.append("")
                continue

            shown = items[:limit]
            total_found += len(shown)

            for i, it in enumerate(shown, start=1):
                sym = it.get("symbol", "?")
                ch = float(it.get("change_pct_24h") or 0.0)
                qv = float(it.get("quote_volume_24h") or 0.0)
                last = float(it.get("last") or 0.0)
                spike = float(it.get("volume_spike") or 0.0)

                icon = "🟩" if ch > 0 else "🟥" if ch < 0 else "🟦"
                lines.append(
                    f"{i}. <code>{sym}</code> {icon} <code>{ch:+.2f}%</code>  "
                    f"<code>{last:g}</code>  spike <code>{spike:.2f}×</code>  vol <code>{qv:,.0f}</code>"
                )

            lines.append("")

        if total_found == 0:
            await m.answer(
                "⚠️ Сейчас scan ничего сильного не нашёл на 15m / 1h / 4h.",
                parse_mode="HTML",
            )
            access_service.consume(user_id, "scan")
            return

        lines.append("Дальше: выбери монету и напиши <code>/plan TICKER</code>.")
        await m.answer("\n".join(lines).strip(), parse_mode="HTML")
        access_service.consume(user_id, "scan")

    except APIError as e:
        await m.answer(f"❌ APIError: {e}", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"❌ Error: {type(e).__name__}: {e}", parse_mode="HTML")
@router.message(F.text == "📘 Guide / Полный гайд")
async def full_guide(m: Message):
    guide = """<b>📘 Guide / Полный гайд</b>

<b>RU</b>
<b>1. /top</b> — показывает самые ликвидные монеты по объёму.
Это быстрый способ понять, где рынок сейчас живой.

<b>2. /scan</b> — показывает активные монеты на <code>15m</code>, <code>1h</code> и <code>4h</code>.
Обычно логика такая: сначала смотришь <code>/scan</code>, потом открываешь <code>/plan</code>.

<b>3. /plan TICKER</b> — показывает структуру, уровни и сценарий.
Пример: <code>/plan BTC_USDT</code>

<b>4. Свободный текст</b> — можно писать обычным языком.
Например: <code>что думаешь по битку</code> или <code>стоит ли шортить solana</code>.

<b>5. Dexter Research</b> — если нужен более подробный разбор.

<i>Важно: бот даёт аналитику, а не финансовый совет.</i>

<b>EN</b>
<b>1. /top</b> — shows the most liquid coins by volume.
This is the fastest way to see where the market is active.

<b>2. /scan</b> — shows active coins on <code>15m</code>, <code>1h</code> and <code>4h</code>.
A common flow is: check <code>/scan</code> first, then open <code>/plan</code>.

<b>3. /plan TICKER</b> — shows structure, levels and scenario.
Example: <code>/plan ETH_USDT</code>

<b>4. Free text</b> — you can type naturally.
For example: <code>what do you think about bitcoin</code>.

<b>5. Dexter Research</b> — use it when you want a deeper read.

<i>Important: this bot provides analysis, not financial advice.</i>"""
    await m.answer(guide, parse_mode="HTML")


@router.message(F.text == "❌ Скрыть кнопки")
async def hide_buttons(m: Message):
    await m.answer("Ок, убрал кнопки. Если нужно вернуть — напиши /start.", reply_markup=ReplyKeyboardRemove())


@router.message(F.text == "🧪 Examples / Примеры")
async def examples(m: Message):
    msg = """<b>🧪 Examples / Примеры</b>

<b>RU</b>
• Найти активные монеты:
<code>/scan</code>

• Посмотреть топ ликвидных монет:
<code>/top</code>
<code>/top 20</code>

• Получить план по монете:
<code>/plan BTC_USDT</code>
<code>/plan ETH_USDT</code>
<code>/plan SOL_USDT</code>

• Написать вопрос своими словами:
<code>что думаешь по битку</code>
<code>стоит ли шортить солану</code>

<b>EN</b>
• Find active coins:
<code>/scan</code>

• See top liquid coins:
<code>/top</code>
<code>/top 20</code>

• Get a plan for a coin:
<code>/plan BTC_USDT</code>
<code>/plan ETH_USDT</code>

• Ask in plain English:
<code>what do you think about bitcoin</code>
<code>should I short solana</code>

Tip: <code>/scan</code> → choose a coin → <code>/plan</code>."""
    await m.answer(msg, parse_mode="HTML")


@router.message(F.text == "✍️ Своя монета")
async def plan_custom_hint(m: Message):
    msg = (
        "<b>Своя монета</b>\n"
        "Напиши команду в любом удобном формате:\n"
        "• <code>/plan ADA_USDT</code>\n"
        "• <code>/plan ada-usdt</code>\n"
        "• <code>/plan ada/usdt</code>\n\n"
        "Подсказка: бот сам нормализует символ.\n\n"
        "Dexter research: добавь слово <code>explain</code> или <code>почему</code>:\n"
        "• <code>/plan ADA_USDT explain</code>"
    )
    await m.answer(msg, parse_mode="HTML")


@router.message(F.text.startswith("/"))
async def any_text(m: Message):
    txt = (m.text or "").strip()
    if not txt or txt.startswith("/"):
        return
    try:
        data = await post("/chat", {"text": txt, "user_id": m.from_user.id})
        await m.answer(data.get("answer_html", "⚠️ empty"), parse_mode="HTML")
    except APIError as e:
        await m.answer(f"❌ API: {e}", parse_mode="HTML")
