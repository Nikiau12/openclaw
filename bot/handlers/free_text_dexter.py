from __future__ import annotations

import re

def strip_ai_block(html: str) -> str:
    """
    Убирает AI-аналитику (Key points / Interpretation / Alignment / Scenarios / Confidence),
    но оставляет News + Sources + OpenClaw plan.
    """
    if not html:
        return html
    # 1) убрать большой <div> с аналитикой (внутри обычно есть <h4>Ключевые пункты</h4>)
    html2 = re.sub(r"<div>\s*<div>🤖 AI:.*?</div>\s*<h4>Ключевые пункты</h4>.*?</div>\s*", "", html, flags=re.S)
    # 2) на всякий случай убрать любые секции с заголовками аналитики, если они не в первом div
    html2 = re.sub(r"<h4>Ключевые пункты</h4>.*?(?=<b>🗂 Sources</b>)", "", html2, flags=re.S)
    html2 = re.sub(r"<h4>Интерпретация</h4>.*?(?=<h4>|<b>🗂 Sources</b>)", "", html2, flags=re.S)
    html2 = re.sub(r"<h4>Согласование</h4>.*?(?=<h4>|<b>🗂 Sources</b>)", "", html2, flags=re.S)
    html2 = re.sub(r"<h4>Сценарии</h4>.*?(?=<div><b>Уверенность:|<b>🗂 Sources</b>)", "", html2, flags=re.S)
    html2 = re.sub(r"<div><b>Уверенность:.*?</div>", "", html2, flags=re.S)
    return html2


import time
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest

from bot.clients.api import post

router = Router()
log = logging.getLogger(__name__)

# UI buttons handled elsewhere — don't intercept
_UI_BUTTONS = {
    "🧠 Dexter Research",
    "⬅️ Назад",
    "📘 Guide / Полный гайд",
    "❌ Скрыть кнопки",
    "🧪 Examples / Примеры",
    "✍️ Своя монета",
}

_SYMBOL_ALIASES = {
    "BTCUSDT": [
        "btc", "bitcoin", "xbt",
        "биток", "битка", "битку",
        "биткоин", "биткоина", "биткоину",
        "биткойн", "биткойна", "биткойну",
    ],
    "ETHUSDT": [
        "eth", "ethereum", "ether",
        "эфир", "эфира", "эфиру",
        "эфириум", "эфириума",
    ],
    "SOLUSDT": [
        "sol", "solana",
        "сол", "солана", "соланы", "солану",
    ],
    "BNBUSDT": [
        "bnb", "binance coin", "бинанс", "бинанс коин",
    ],
    "XRPUSDT": [
        "xrp", "ripple", "рипл", "рипла",
    ],
    "ADAUSDT": [
        "ada", "cardano", "кардано",
    ],
    "DOGEUSDT": [
        "doge", "dogecoin", "дог", "доги", "догикоин", "додж", "доджкоин",
    ],
    "LINKUSDT": [
        "link", "chainlink", "чейнлинк",
    ],
    "AVAXUSDT": [
        "avax", "avalanche", "авакс", "аваланч",
    ],
    "SUIUSDT": [
        "sui", "суи",
    ],
}

_SYMBOL_STEMS = {
    "BTCUSDT": ["битко", "биткой", "биток", "bitcoin", "btc", "xbt"],
    "ETHUSDT": ["эфир", "эфири", "ethereum", "ether", "eth"],
    "SOLUSDT": ["солан", "solana", "sol"],
    "BNBUSDT": ["bnb", "бинанс"],
    "XRPUSDT": ["xrp", "рипл", "ripple"],
    "ADAUSDT": ["ada", "cardano", "кардан"],
    "DOGEUSDT": ["doge", "dogecoin", "додж", "дог"],
    "LINKUSDT": ["link", "chainlink", "чейнлинк"],
    "AVAXUSDT": ["avax", "avalanche", "авакс", "аваланч"],
    "SUIUSDT": ["sui", "суи"],
}

_AI_HINTS = [
    " ai",
    "анализ",
    "подроб",
    "разбор",
    "что думаешь",
    "что скажешь",
    "мнение",
    "вход",
    "войти",
    "сделк",
    "сетап",
    "сценари",
    "стоп",
    "риск",
    "long",
    "short",
    "лонг",
    "шорт",
    "entry",
    "setup",
    "invalidation",
]

def _looks_like_symbol_only(text: str) -> bool:
    t = (text or "").strip().upper()
    return bool(re.fullmatch(r"[A-Z]{2,10}(?:[/_-]?[A-Z]{3,6})", t))

def _should_handle(txt: str) -> bool:
    t = (txt or "").strip()
    if not t:
        return False
    if t in _UI_BUTTONS:
        return False
    if t.startswith("🧠 "):  # handled in chat.py
        return False
    # ticker-only or longer natural language
    if _looks_like_symbol_only(t):
        return True
    if len(t) >= 8:
        return True
    return False

def _normalize_query(text: str) -> str:
    q = (text or "").strip()
    q = re.sub(r"\s+", " ", q).strip()
    if not q:
        return ""
    q = q[:700]
    if _looks_like_symbol_only(q):
        return f"{q} news"
    return q

def _extract_symbol_from_text(text: str) -> str | None:
    t = (text or "").strip().lower()
    if not t:
        return None

    # 1) direct ticker-like text
    raw = (text or "").strip().upper().replace("-", "").replace("/", "").replace("_", "")
    if raw.endswith("USDT") and re.fullmatch(r"[A-Z]{2,12}USDT", raw):
        return raw
    if re.fullmatch(r"[A-Z]{2,10}", raw):
        return raw + "USDT"

    # 2) exact alias dictionary
    padded = f" {t} "
    for symbol, aliases in _SYMBOL_ALIASES.items():
        for alias in aliases:
            a = alias.lower().strip()
            if not a:
                continue
            if re.search(rf"(^|[^a-zа-я0-9]){re.escape(a)}([^a-zа-я0-9]|$)", padded, flags=re.IGNORECASE):
                return symbol

    # 3) stem match for russian word forms / variants
    for symbol, stems in _SYMBOL_STEMS.items():
        for stem in stems:
            st = stem.lower().strip()
            if st and st in t:
                return symbol

    return None

def _wants_ai_from_text(text: str) -> bool:
    t = " " + ((text or "").strip().lower()) + " "
    return any(h in t for h in _AI_HINTS)

def _chunk_text(text: str, max_len: int = 3500) -> list[str]:
    t = text or ""
    if len(t) <= max_len:
        return [t]
    return [t[i:i + max_len] for i in range(0, len(t), max_len)]

def _html_to_plain(html: str) -> str:
    # rough but works for Telegram fallback
    t = html or ""
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</p\s*>", "\n\n", t, flags=re.I)
    t = re.sub(r"</li\s*>", "\n", t, flags=re.I)
    t = re.sub(r"<li\s*>", "• ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    # basic entities
    t = t.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"')
    return t.strip()

def _normalize_telegram_html(html: str) -> str:
    t = html or ""
    # Telegram HTML: <br> is OK, <br/> is NOT
    t = re.sub(r"<br\s*/\s*>", "<br>", t, flags=re.I)
    t = re.sub(r"<br\s*/>", "<br>", t, flags=re.I)
    t = t.replace("</br>", "<br>").replace("</BR>", "<br>")
    return t
async def safe_send_html(message: Message, html: str, extra_html: str = "") -> None:
    body_html = (html or "") + (extra_html or "")
    plain = _html_to_plain(body_html)
    plain = plain.replace("<", "⟨").replace(">", "⟩")
    if not plain.strip():
        plain = "Dexter response empty"
    for part in _chunk_text(plain, 3500):
        if part.strip():
            await message.answer(part, parse_mode=None)

@router.message(F.text & ~F.text.startswith("/"))
async def free_text_to_dexter(message: Message):
    txt = (message.text or "").strip()
    if not _should_handle(txt):
        return

    q = _normalize_query(txt)
    if not q:
        return

    want_ai = _wants_ai_from_text(q)
    q_clean = re.sub(r"\s+ai\s*$", "", q, flags=re.IGNORECASE).strip()
    sym = _extract_symbol_from_text(q_clean)

    if sym and not _looks_like_symbol_only(q_clean):
        q_clean = q_clean[:700]

    # 1) PLAN-FIRST всегда
    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    except Exception:
        pass

    t0 = time.monotonic()
    try:
        plan_payload = {"query": q_clean, "analysis": False}
        if sym:
            plan_payload["symbol"] = sym
        plan_data = await post("/dexter/chat", plan_payload, timeout=20)
        plan_dt = time.monotonic() - t0
        plan_html = (plan_data or {}).get("message_html") if isinstance(plan_data, dict) else None
        plan_html = strip_ai_block(plan_html) if plan_html else plan_html
        plan_extra = "\n\n<i>⏱ plan {:.1f}s</i>".format(plan_dt)
        await safe_send_html(message, plan_html or "<i>Dexter unavailable</i>", plan_extra)
    except Exception:
        log.exception("free_text_dexter: plan-first failed q=%r sym=%r", q_clean, sym)
        await message.answer("⚠️ Dexter временно недоступен. Попробуй ещё раз через минуту.")
        return

    # 2) AI вторым сообщением, только если want_ai
    if want_ai:
        t1 = time.monotonic()
        try:
            ai_payload = {"query": q_clean, "analysis": True}
            if sym:
                ai_payload["symbol"] = sym
            ai_data = await post("/dexter/chat", ai_payload, timeout=45)
            ai_dt = time.monotonic() - t1
            ai_html = (ai_data or {}).get("message_html") if isinstance(ai_data, dict) else None
            ai_extra = "\n\n<i>⏱ ai {:.1f}s</i>".format(ai_dt)
            await safe_send_html(message, ai_html or "<i>AI empty</i>", ai_extra)
        except Exception:
            log.exception("free_text_dexter: ai follow-up failed q=%r sym=%r", q_clean, sym)
            await message.answer("🤖 AI: OFF • timeout/error")
