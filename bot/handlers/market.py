from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from bot.clients.api import get, APIError

router = Router()

@router.message(Command("market"))
async def market_cmd(message: Message):
    parts = message.text.split()

    if len(parts) < 2:
        await message.answer("Используй: /market BTC или /market pepeusdt")
        return

    user_input = parts[1]

    try:
        data = await get("/mexc/summary", {"symbol": user_input})
        await message.answer(data["summary_html"])
    except APIError as e:
        await message.answer(f"Ошибка API: {e}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
