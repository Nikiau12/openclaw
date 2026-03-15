from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.access import AccessService
from bot.clients.api import post, APIError
from bot.handlers.pro import LIMIT_REACHED_MESSAGE_RU, pro_keyboard

router = Router()
access_service = AccessService()

_VERDICT_ICON = {
    "bullish": "🟩",
    "bearish": "🟥",
    "neutral": "🟦",
    "conflicted": "⚠️",
}


@router.message(Command("insight"))
async def insight_command(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /insight BTCUSDT")
        return

    symbol = parts[1].strip().upper()
    user_id = message.from_user.id

    decision = access_service.check(user_id, "analytics")
    if not decision.allowed:
        await message.answer(
            LIMIT_REACHED_MESSAGE_RU,
            reply_markup=pro_keyboard(user_id),
        )
        return

    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        data = await post("/insight", {"symbol": symbol})
    except APIError as e:
        await message.answer(f"⚠️ API: {e}")
        return

    icon = _VERDICT_ICON.get(data.get("verdict", ""), "❓")
    news_line = "" if data.get("chart_only") else f"\n📰 <b>Новости:</b> {data.get('news_sentiment', '—')}"
    conflicts = "\n".join(f"⚡️ {c}" for c in data.get("conflicts", []))

    text = (
        f"{icon} <b>{data.get('symbol', symbol)}</b> — <b>{str(data.get('verdict', 'neutral')).upper()}</b>\n\n"
        f"📊 <b>Чарт:</b> {data.get('bias', 'NEUTRAL')}"
        f"{news_line}\n"
        f"🏗 <b>Структура:</b> {data.get('structure_note') or '—'}\n"
        f"🎯 <b>POC:</b> {float(data.get('poc', 0.0)):.4f}  |  <b>Last:</b> {float(data.get('last_price', 0.0)):.4f}"
        + (f"\n\n{conflicts}" if conflicts else "")
        + ("\n\n<i>ℹ️ Новости недоступны — вывод построен только по чарту</i>" if data.get("chart_only") else "")
    )

    access_service.consume(user_id, "analytics")
    await message.answer(text, parse_mode="HTML")
