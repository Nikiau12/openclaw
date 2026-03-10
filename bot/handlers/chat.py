import asyncio
import re
from typing import List, Tuple

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from bot.clients.api import get, post, APIError

router = Router()

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
            [KeyboardButton(text="📘 Полный гайд"), KeyboardButton(text="🧪 Примеры")],
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
        "Нужны детали — нажми <b>📘 Полный гайд</b>.\n"
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
    raw = (m.text or "").replace("🧠", "").strip()
    symbol = _normalize_symbol(raw)

    # Try Dexter -> fallback to normal plan
    try:
        dex = await post("/dexter/chat", {"query": symbol, "symbol": symbol, "analysis": True})
        if isinstance(dex, dict) and dex.get("ok") and dex.get("message_html"):
            await m.answer(dex["message_html"], parse_mode="HTML", disable_web_page_preview=True)
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
    except APIError as e:
        await m.answer(f"❌ APIError: {e}", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"❌ Error: {type(e).__name__}: {e}", parse_mode="HTML")


@router.message(Command("plan"))
async def plan(m: Message):
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

        tf = "5m"
        mult = 1.5
        limit = 10

        if len(parts) > 1:
            tf = parts[1].strip()
        if len(parts) > 2:
            try:
                mult = float(parts[2])
            except Exception:
                mult = 1.5
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
            "candidate_pool": 80,
            "min_quote_volume_24h": 5_000_000,
            "max_abs_change_24h": 40,
            "volume_spike": {
                "tf": tf,
                "lookback": 20,
                "multiplier": mult,
                "limit": 80
            }
        }

        data = await post("/market/scan", payload)
        if isinstance(data, dict) and data.get("message_html"):
            await m.answer(data["message_html"], parse_mode="HTML", disable_web_page_preview=True)
            return

        items = data.get("items", []) if isinstance(data, dict) else []

        if not items:
            await m.answer(f"⚠️ Ничего не нашёл (tf={tf}, spike>={mult}).", parse_mode="HTML")
            return

        # --- trend filter: fetch bias for top N ---
        top_n = min(5, len(items))
        symbols = [items[i].get("symbol", "") for i in range(top_n)]
        symbols = [s for s in symbols if s]

        async def fetch_bias(sym: str):
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
        # (оставь твой большой guide тут без изменений)
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
        "• Dexter research (без новой команды):\n"
        "<code>/plan BTC_USDT explain</code>\n"
        "<code>/plan BTC_USDT почему</code>\n\n"
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
