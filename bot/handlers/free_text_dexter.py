from __future__ import annotations

import re
import time
from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ChatAction

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
    try:
        await message.answer((html or "<i>Dexter unavailable</i>") + extra)
    except Exception as e:
        # fallback: send plain text if HTML/length fails
        await message.answer(f"⚠️ Telegram send failed: {type(e).__name__}")
