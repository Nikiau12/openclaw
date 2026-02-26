from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from bot.clients.api import post, APIError

router = Router()

@router.message(Command("start"))
async def start(m: Message):
    await m.answer(
        "Привет 👋\n"
        "Пиши вопрос обычным текстом.\n"
        "Команда: /plan BTC_USDT — получить план.\n",
        parse_mode="HTML"
    )

@router.message(Command("plan"))
async def plan(m: Message):
    parts = (m.text or "").split(maxsplit=1)
    symbol = parts[1].strip() if len(parts) > 1 else "BTC_USDT"
    try:
        data = await post("/plan/v3", {"symbol": symbol})
        msg = data.get("message_html") if isinstance(data, dict) else None
        await m.answer(msg or "⚠️ empty", parse_mode="HTML")
    except APIError as e:
        await m.answer(f"❌ APIError: {e}", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"❌ Error: {type(e).__name__}: {e}", parse_mode="HTML")


@router.message()
async def any_text(m: Message):
    txt = (m.text or "").strip()
    if not txt or txt.startswith("/"):
        return
    try:
        data = await post("/chat", {"text": txt, "user_id": m.from_user.id})
        await m.answer(data.get("answer_html", "⚠️ empty"), parse_mode="HTML")
    except APIError as e:
        await m.answer(f"❌ API: {e}", parse_mode="HTML")
