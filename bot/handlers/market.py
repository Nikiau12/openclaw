from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from bot.clients.api import get, APIError

router = Router()

@router.message(Command("market"))
async def market_cmd(message: Message):
    parts = message.text.split()

    if len(parts) < 2:
        await message.answer(
            "<b>/market</b> — быстрая сводка по монете: цена, изменение и объём.\n\n"
            "Примеры:\n"
            "• <code>/market BTC</code>\n"
            "• <code>/market PEPEUSDT</code>",
            parse_mode="HTML",
        )
        return

    user_input = parts[1]

    try:
        data = await get("/mexc/summary", {"symbol": user_input})
        await message.answer(data["summary_html"])
    except APIError as e:
        await message.answer("⚠️ Не удалось получить сводку по монете. Попробуй ещё раз через минуту.")
    except Exception as e:
        await message.answer("⚠️ Что-то пошло не так. Попробуй ещё раз через минуту.")
