from __future__ import annotations

import re
import time
from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest

from bot.clients.api import post

router = Router()

# UI buttons handled elsewhere — don't intercept
_UI_BUTTONS = {
    "🧠 Dexter Research",
    "⬅️ Назад",
    "📘 Полный гайд",
    "❌ Скрыть кнопки",
    "🧪 Примеры",
    "✍️ Своя монета",
}

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

    # UX
    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    except Exception:
        pass
    await message.answer("⏳ Думаю… (Dexter + AI)")

    t0 = time.monotonic()
    try:
        data = await post("/dexter/run?analysis=1", {"query": q, "analysis": True}, timeout=20)
    except Exception:
        await message.answer("⚠️ Таймаут/ошибка при запросе Dexter. Попробуй ещё раз через минуту.")
        return

    dt = time.monotonic() - t0
    html = (data or {}).get("message_html") if isinstance(data, dict) else None
    extra = "\n\n<i>⏱ dexter {:.1f}s</i>".format(dt)
    await safe_send_html(message, html or "<i>Dexter unavailable</i>", extra)
