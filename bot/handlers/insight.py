from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.access import AccessService
from bot.clients.api import post, APIError
from bot.handlers.pro import LIMIT_REACHED_MESSAGE_RU, pro_keyboard


router = Router()
access_service = AccessService()

def _usage_hint(user_id: int, feature: str) -> str:
    decision = access_service.check(user_id, feature)
    if decision.is_pro:
        return ""
    used = decision.limit - decision.remaining
    return f"\n\n<i>💡 Использовано {used} из {decision.limit} бесплатных запросов. /pro — безлимит.</i>"

_VERDICT_ICON = {
    "bullish": "🟩",
    "bearish": "🟥",
    "neutral": "🟦",
    "conflicted": "⚠️",
}

def _insight_summary(data: dict) -> str:
    bias = str(data.get("bias", "NEUTRAL")).upper()
    news = str(data.get("news_sentiment", "unavailable")).lower()
    verdict = str(data.get("verdict", "neutral")).lower()
    chart_only = bool(data.get("chart_only"))

    if chart_only:
        if bias == "BULLISH":
            return "Чарт остаётся бычьим. Новости сейчас недоступны, вывод построен только по структуре."
        if bias == "BEARISH":
            return "Чарт остаётся медвежьим. Новости сейчас недоступны, вывод построен только по структуре."
        return "Чёткой направленности по чарту нет. Новости сейчас недоступны, вывод построен только по структуре."

    if verdict == "conflicted":
        return "Чарт и новостной фон сейчас противоречат друг другу — сигнал менее чистый."
    if bias == "BULLISH" and news == "bullish":
        return "Чарт и новостной фон смотрят в одну сторону: фон скорее бычий."
    if bias == "BEARISH" and news == "bearish":
        return "Чарт и новостной фон смотрят в одну сторону: фон скорее медвежий."
    if bias == "BULLISH":
        return "Чарт остаётся бычьим, но новостной фон не даёт сильного дополнительного подтверждения."
    if bias == "BEARISH":
        return "Чарт остаётся медвежьим, но новостной фон не даёт сильного дополнительного подтверждения."
    return "Рынок выглядит смешанно: явного преимущества по направлению сейчас нет."


@router.message(Command("insight"))
async def insight_command(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "<b>/insight</b> — анализ структуры + новостной фон по монете.\n\n"
            "Пример: <code>/insight BTC_USDT</code>",
            parse_mode="HTML",
        )
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
        await message.answer("⚠️ Не удалось получить insight. Попробуй ещё раз через минуту.")
        return

    icon = _VERDICT_ICON.get(data.get("verdict", ""), "❓")
    news_line = "" if data.get("chart_only") else f"\n📰 <b>Новости:</b> {data.get('news_sentiment', '—')}"
    conflicts = "\n".join(f"⚡️ {c}" for c in data.get("conflicts", []))

    summary = _insight_summary(data)

    text = (
        f"{icon} <b>{data.get('symbol', symbol)}</b> — <b>{str(data.get('verdict', 'neutral')).upper()}</b>\n\n"
        f"🧭 <b>Вывод:</b> {summary}\n\n"
        f"📊 <b>Чарт:</b> {data.get('bias', 'NEUTRAL')}"
        f"{news_line}\n"
        f"🏗 <b>Структура:</b> {data.get('structure_note') or '—'}\n"
        f"🎯 <b>POC:</b> {float(data.get('poc', 0.0)):.4f}  |  <b>Last:</b> {float(data.get('last_price', 0.0)):.4f}"
        + (f"\n\n{conflicts}" if conflicts else "")
        + ("\n\n<i>ℹ️ Новости недоступны — вывод построен только по чарту</i>" if data.get("chart_only") else "")
    )

    access_service.consume(user_id, "analytics")
    text += _usage_hint(user_id, "analytics")
    await message.answer(text, parse_mode="HTML")
