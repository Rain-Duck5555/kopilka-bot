import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from database.db import (
    get_user,
    get_categories,
    get_category_by_name,
    add_transaction,
    can_add_transaction,
    increment_operations,
)
from utils.keyboards import (
    main_menu_kb, categories_kb, cancel_kb, back_to_menu_kb,
)

logger = logging.getLogger(__name__)
router = Router()


class AddTransaction(StatesGroup):
    waiting_amount = State()
    waiting_category = State()


@router.callback_query(F.data == "add_expense")
async def cb_add_expense(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddTransaction.waiting_amount)
    await state.update_data(type_="expense")

    await callback.message.edit_text(
        "💸 <b>Добавление траты</b>\n\n"
        "Напиши сумму (только число), например: <code>300</code>",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "add_income")
async def cb_add_income(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddTransaction.waiting_amount)
    await state.update_data(type_="income")

    await callback.message.edit_text(
        "💰 <b>Добавление дохода</b>\n\n"
        "Напиши сумму (только число), например: <code>80000</code>",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(AddTransaction.waiting_amount)
async def process_amount(message: Message, state: FSMContext):
    text = (message.text or "").strip().replace(",", ".").replace(" ", "")

    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Не понял сумму. Напиши просто число, например: <code>300</code>",
            reply_markup=cancel_kb()
        )
        return

    data = await state.get_data()
    type_ = data["type_"]

    # Проверяем лимит
    can_add, remaining = await can_add_transaction(message.from_user.id)

    if not can_add:
        await state.clear()
        await message.answer(
            "🔒 <b>Лимит бесплатных операций исчерпан</b>\n\n"
            "В бесплатном тарифе доступно <b>50 операций в месяц</b>.\n\n"
            "💎 Оформи <b>Pro-подписку за 299₽/мес</b>, и получишь:\n"
            "• Неограниченное количество операций\n"
            "• Аналитику с топ-5 категорий\n"
            "• ИИ-инсайты по твоим тратам\n\n"
            "Команда: /subscribe",
            reply_markup=cancel_kb()
        )
        return

    await state.update_data(amount=amount)

    # Загружаем категории из БД
    categories = await get_categories(message.from_user.id, type_)

    emoji = "💸" if type_ == "expense" else "💰"
    title = "траты" if type_ == "expense" else "дохода"

    await state.set_state(AddTransaction.waiting_category)
    await message.answer(
        f"{emoji} Сумма: <b>{amount:,.0f}₽</b>\n\n"
        f"Выбери категорию {title}:",
        reply_markup=categories_kb(categories, type_)
    )


@router.callback_query(AddTransaction.waiting_category, F.data.startswith("cat:"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    _, type_, cat_id = callback.data.split(":")
    cat_id = int(cat_id)

    data = await state.get_data()
    amount = data["amount"]

    await add_transaction(
        user_id=callback.from_user.id,
        amount=amount,
        type_=type_,
        category_id=cat_id,
        comment=None,
    )

    # Увеличиваем счётчик операций
    await increment_operations(callback.from_user.id)

    await state.clear()

    emoji = "💸" if type_ == "expense" else "💰"
    type_text = "Расход" if type_ == "expense" else "Доход"

    await callback.message.edit_text(
        f"✅ <b>{type_text} записан!</b>\n\n"
        f"Сумма: <b>{amount:,.0f}₽</b>",
        reply_markup=back_to_menu_kb()
    )
    await callback.answer("Сохранено")


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🏠 <b>Главное меню</b>\n\nВыбери, что хочешь сделать:",
        reply_markup=main_menu_kb()
    )
    await callback.answer("Отменено")