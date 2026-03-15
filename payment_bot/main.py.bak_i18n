import asyncio
import re
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.types import Message

from payment_bot.config import PAYMENT_ADMIN_ID, PAYMENT_BOT_TOKEN, PAYMENT_STATE_PATH
from payment_bot.storage.payment_store import JsonPaymentStore

router = Router()
store = JsonPaymentStore(PAYMENT_STATE_PATH)
UTC = timezone.utc


def _parse_start_payload(text: str) -> int | None:
    raw = (text or "").strip()
    m = re.match(r"^/start\s+pay_(\d+)$", raw)
    if not m:
        return None
    return int(m.group(1))


def _looks_like_tx_hash(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.fullmatch(r"[A-Fa-f0-9]{32,128}", t))


@router.message(CommandStart())
async def start(message: Message) -> None:
    source_user_id = _parse_start_payload(message.text or "")
    if source_user_id is not None:
        store.set_session_target(message.from_user.id, source_user_id)
        await message.answer(
            "Привет.\n\n"
            "Этот бот принимает TX hash для оплаты подписки.\n\n"
            "Пришли hash одним сообщением.\n"
            "После этого заявка уйдёт на проверку."
        )
        return

    await message.answer(
        "Привет.\n\n"
        "Этот бот нужен только для отправки TX hash после оплаты подписки.\n\n"
        "Открой его по кнопке из основного бота."
    )


@router.message(F.text)
async def receive_hash(message: Message) -> None:
    txt = (message.text or "").strip()
    if txt.startswith("/"):
        return

    source_user_id = store.get_session_target(message.from_user.id)
    if source_user_id is None:
        await message.answer(
            "Сначала открой этого бота по кнопке из основного бота, "
            "чтобы я понял, кому привязать оплату."
        )
        return

    if not _looks_like_tx_hash(txt):
        await message.answer("Это не похоже на TX hash. Отправь hash одной строкой.")
        return

    if store.tx_hash_exists(txt):
        await message.answer("Этот TX hash уже был отправлен ранее.")
        return

    payload = {
        "source_user_id": source_user_id,
        "submitter_user_id": message.from_user.id,
        "submitter_username": message.from_user.username,
        "submitter_name": message.from_user.full_name,
        "tx_hash": txt,
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
    }
    store.add_request(payload)

    await message.answer(
        "Hash получен.\n\n"
        "Заявка отправлена на проверку. После подтверждения оплаты доступ будет активирован."
    )

    if PAYMENT_ADMIN_ID:
        admin_msg = (
            "<b>Новая заявка на оплату</b>\n\n"
            f"<b>source_user_id:</b> <code>{source_user_id}</code>\n"
            f"<b>submitter_user_id:</b> <code>{message.from_user.id}</code>\n"
            f"<b>username:</b> <code>{message.from_user.username or '-'}</code>\n"
            f"<b>name:</b> <code>{message.from_user.full_name}</code>\n"
            f"<b>tx_hash:</b>\n<code>{txt}</code>"
        )
        await message.bot.send_message(PAYMENT_ADMIN_ID, admin_msg, parse_mode="HTML")


async def main() -> None:
    if not PAYMENT_BOT_TOKEN:
        raise SystemExit("PAYMENT_BOT_TOKEN is empty")

    bot = Bot(
        token=PAYMENT_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
