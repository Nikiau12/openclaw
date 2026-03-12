from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import ADMIN_USER_IDS, TRC20_ADDRESS, SECOND_BOT_USERNAME
from bot.services.access import AccessService

router = Router()
access_service = AccessService()


def pro_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Открыть Pro", callback_data="open_pro")]]

    if user_id and SECOND_BOT_USERNAME:
        rows.append([
            InlineKeyboardButton(
                text="Отправить hash",
                url=f"https://t.me/{SECOND_BOT_USERNAME}?start=pay_{user_id}",
            )
        ])
    else:
        rows.append([InlineKeyboardButton(text="Я оплатил", callback_data="paid_pro")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_message() -> str:
    return (
        "<b>MarketAnalyst Pro</b>\n\n"
        "Стоимость: <b>29 USDT / month</b>\n"
        "Сеть: <b>TRC20</b>\n"
        f"Адрес: <code>{TRC20_ADDRESS}</code>\n\n"
        "После оплаты:\n"
        "1. Отправь ровно <b>29 USDT</b> в сети <b>TRC20</b>\n"
        "2. Нажми кнопку <b>Отправить hash</b>\n"
        "3. Во втором боте отправь TX hash\n\n"
        "После проверки оплата будет подтверждена, и доступ активируется."
    )


LIMIT_REACHED_MESSAGE_RU = (
    "Лимит бесплатного доступа исчерпан.\n\n"
    "Чтобы продолжить пользоваться ботом без ограничений, открой MarketAnalyst Pro."
)


@router.message(Command("pro"))
async def pro_command(message: Message) -> None:
    await message.answer(payment_message(), reply_markup=pro_keyboard(message.from_user.id))


@router.message(F.text.func(lambda s: isinstance(s, str) and s.strip().upper() == "PRO"))
async def pro_text(message: Message) -> None:
    await message.answer(payment_message(), reply_markup=pro_keyboard(message.from_user.id))


@router.callback_query(F.data == "open_pro")
async def pro_open_callback(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer(payment_message(), reply_markup=pro_keyboard(callback.from_user.id))
    await callback.answer()


@router.callback_query(F.data == "paid_pro")
async def pro_paid_callback(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer("Нажми кнопку «Отправить hash» и перейди во второй бот.")
    await callback.answer()


@router.message(Command("pro_status"))
async def pro_status(message: Message) -> None:
    user_id = message.from_user.id
    state = access_service.get_user_state(user_id)
    await message.answer(
        f"<b>Plan:</b> <code>{state.get('plan')}</code>\n"
        f"<b>Expires:</b> <code>{state.get('expires_at')}</code>\n"
        f"<b>Usage:</b> <code>{state.get('usage')}</code>",
        parse_mode="HTML",
    )


@router.message(Command("grant_pro"))
async def grant_pro(message: Message) -> None:
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Access denied.")
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Usage: /grant_pro <user_id> [days]")
        return

    try:
        target_user_id = int(parts[1])
        days = int(parts[2]) if len(parts) > 2 else 30
    except ValueError:
        await message.answer("Usage: /grant_pro <user_id> [days]")
        return

    access_service.activate_pro(target_user_id, days=days)
    state = access_service.get_user_state(target_user_id)
    await message.answer(
        f"Pro activated for <code>{target_user_id}</code> until <code>{state.get('expires_at')}</code>.",
        parse_mode="HTML",
    )
