import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from config import BOT_TOKEN
from database.db import init_db, get_user, create_user
from handlers import menu, add_transaction
from utils.keyboards import main_menu_kb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Подключаем роутеры
dp.include_router(menu.router)
dp.include_router(add_transaction.router)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    tg_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "друг"

    user = await get_user(tg_id)

    if user is None:
        await create_user(tg_id, username, first_name)
        logger.info(f"🆕 Новый юзер: {tg_id} ({first_name})")
        greeting = (
            f"Добро пожаловать, {first_name}! 🎉\n\n"
            f"Я — <b>Копилка</b>, твой умный финансовый помощник.\n\n"
            f"Записывай траты и доходы, следи за балансом."
        )
    else:
        greeting = f"С возвращением, {first_name}! 👋"

    await message.answer(greeting, reply_markup=main_menu_kb())


async def main():
    logger.info("🚀 Запускаю бота...")

    await init_db()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⛔ Бот остановлен")