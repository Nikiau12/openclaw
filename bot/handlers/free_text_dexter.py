from __future__ import annotations

import re
import time
from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ChatAction

from bot.clients.api import post

router = Router()

# UI buttons handled in handlers/chat.py — do NOT intercept here
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

def _normalize_query(text: str) -> str:
    q = (text or "").strip()
    q = re.sub(r"\s+", " ", q).strip()
    if not q:
        return ""
    q = q[:700]
    if _looks_like_symbol_only(q):
        return f"{q} news"
    return q

@router.message(
    F.text
    & ~F.text.startswith("/")
    & ~F.text.in_(_UI_BUTTONS)
    & ~F.text.startswith("🧠 ")
)
async def free_text_to_dexter(message: Message):
    txt = (message.text or "").strip()
    q = _normalize_query(txt)
    if not q:
        return

    # UX: show typing + progress
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
    await message.answer((html or "<i>Dexter unavailable</i>") + f"\n\n<i>⏱ {dt:.1f}s</i>")
