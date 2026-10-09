import logging

from aiogram import Router
from aiogram.types import Message

from database.db import (
    get_user,
    add_transaction,
    get_category_by_name,
    can_add_transaction,
    increment_operations,
)
from services.llm import parse_transaction

logger = logging.getLogger(__name__)
router = Router()


@router.message()
async def handle_text(message: Message):
    """Обрабатывает любой текст — пытается распарсить как транзакцию."""
    tg_id = message.from_user.id
    text = message.text

    if not text:
        return

    # Проверяем, что юзер зарегистрирован
    user = await get_user(tg_id)
    if user is None:
        await message.answer("Сначала напиши /start.")
        return

    # Показываем "печатает..."
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Отправляем в ИИ
    data = await parse_transaction(text)

    if data is None:
        await message.answer(
            "🤔 Не понял, это не похоже на трату или доход.\n\n"
            "Попробуй так:\n"
            "• <code>кофе 300</code>\n"
            "• <code>такси 450</code>\n"
            "• <code>получил зарплату 80000</code>\n\n"
            "Или используй кнопки в /menu"
        )
        return

    amount = data.get("amount")
    type_ = data.get("type")
    category_name = data.get("category")
    comment = data.get("comment")

    # Проверяем лимит ПЕРЕД сохранением
    can_add, remaining = await can_add_transaction(tg_id)

    if not can_add:
        await message.answer(
            "🔒 <b>Лимит бесплатных операций исчерпан</b>\n\n"
            "В бесплатном тарифе доступно <b>50 операций в месяц</b>.\n\n"
            "💎 Оформи <b>Pro-подписку за 299₽/мес</b>, и получишь:\n"
            "• Неограниченное количество операций\n"
            "• Аналитику с топ-5 категорий\n"
            "• ИИ-инсайты по твоим тратам\n\n"
            "Команда: /subscribe"
        )
        return

    # Ищем категорию в БД
    category_id = None
    if category_name and type_:
        cat = await get_category_by_name(tg_id, category_name, type_)
        if cat:
            category_id = cat["id"]

    # Сохраняем
    await add_transaction(tg_id, amount, type_, category_id, comment)

    # Увеличиваем счётчик
    await increment_operations(tg_id)

    # Отвечаем
    emoji = "💸" if type_ == "expense" else "💰"
    type_text = "Расход" if type_ == "expense" else "Доход"

    await message.answer(
        f"{emoji} <b>{type_text} записан!</b>\n\n"
        f"Сумма: <b>{amount:,.0f}₽</b>\n"
        f"Категория: <b>{category_name or '—'}</b>\n"
        f"Комментарий: {comment or '—'}"
    )