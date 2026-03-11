from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import ADMIN_USER_IDS, TRC20_ADDRESS
from bot.services.access import AccessService

router = Router()
access_service = AccessService()


def pro_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть Pro", callback_data="open_pro")],
            [InlineKeyboardButton(text="Я оплатил", callback_data="paid_pro")],
        ]
    )


def payment_message() -> str:
    return (
        "Открыть доступ к MarketAnalyst Pro\n\n"
        "Стоимость: 29 USDT / месяц\n"
        "Сеть: TRC20\n"
        f"Адрес: {TRC20_ADDRESS}\n\n"
        "После оплаты отправь в этот чат свой TX hash.\n\n"
        "Доступ будет активирован после подтверждения оплаты."
    )


LIMIT_REACHED_MESSAGE_RU = (
    "Лимит бесплатного доступа исчерпан.\n\n"
    "Чтобы продолжить пользоваться ботом без ограничений, открой MarketAnalyst Pro."
)


@router.message(Command("pro"))
async def pro_command(message: Message) -> None:
    await message.answer(payment_message(), reply_markup=pro_keyboard())


@router.message(F.text.func(lambda s: isinstance(s, str) and s.strip().upper() == "PRO"))
async def pro_text(message: Message) -> None:
    await message.answer(payment_message(), reply_markup=pro_keyboard())


@router.callback_query(F.data == "open_pro")
async def pro_open_callback(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer(payment_message(), reply_markup=pro_keyboard())
    await callback.answer()


@router.callback_query(F.data == "paid_pro")
async def pro_paid_callback(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer("Отправь в этот чат свой TX hash.")
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
