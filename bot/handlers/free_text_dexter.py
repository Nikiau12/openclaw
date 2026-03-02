from __future__ import annotations

import re
from aiogram import Router, F
from aiogram.types import Message

from bot.clients.api import post

router = Router()

def _looks_like_symbol_only(text: str) -> bool:
    t = (text or "").strip().upper()
    # BTCUSDT / BTC_USDT / BTC-USDT / ADA/USDT
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

@router.message(F.text & ~F.text.startswith("/"))
async def free_text_to_dexter(message: Message):
    txt = (message.text or "").strip()
    if not txt:
        return

    # don't intercept the menu button label
    if txt == "🧠 Dexter Research":
        return

    q = _normalize_query(txt)
    if not q:
        return

    # quick UX: show we're working
    await message.answer("⏳ Думаю… (Dexter + AI)")

    try:
        # Use shorter timeout for responsiveness
        data = await post("/dexter/run?analysis=1", {"query": q, "analysis": True}, timeout=20)
    except Exception:
        await message.answer("⚠️ Таймаут/ошибка при запросе Dexter. Попробуй ещё раз через минуту.")
        return

    html = (data or {}).get("message_html") if isinstance(data, dict) else None
    await message.answer(html or "<i>Dexter unavailable</i>")
