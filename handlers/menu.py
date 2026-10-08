
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from database.db import (
    get_user, get_month_stats, get_last_transactions,
    get_categories, delete_last_transaction,
)
from utils.keyboards import main_menu_kb, back_to_menu_kb

logger = logging.getLogger(__name__)
router = Router()


async def show_main_menu(message: Message, edit: bool = False):
    """Показывает главное меню."""
    text = (
        "🏠 <b>Главное меню</b>\n\n"
        "Выбери, что хочешь сделать:"
    )
    kb = main_menu_kb()

    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await show_main_menu(message)


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    await show_main_menu(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery):
    tg_id = callback.from_user.id

    income = await get_month_stats(tg_id, "income")
    expense = await get_month_stats(tg_id, "expense")
    balance = income - expense

    text = (
        f"📊 <b>Статистика за этот месяц</b>\n\n"
        f"💰 Доходы: <b>{income:,.0f}₽</b>\n"
        f"💸 Расходы: <b>{expense:,.0f}₽</b>\n"
        f"⚖️ Баланс: <b>{balance:,.0f}₽</b>"
    )

    await callback.message.edit_text(text, reply_markup=back_to_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "history")
async def cb_history(callback: CallbackQuery):
    tg_id = callback.from_user.id
    transactions = await get_last_transactions(tg_id, limit=10)

    if not transactions:
        text = "📜 <b>История пуста</b>\n\nТы ещё не добавил ни одной операции."
    else:
        lines = ["📜 <b>Последние 10 операций:</b>\n"]
        for t in transactions:
            emoji = "💸" if t["type"] == "expense" else "💰"
            sign = "−" if t["type"] == "expense" else "+"
            cat_emoji = t["category_emoji"] or "📁"
            cat_name = t["category_name"] or "—"
            comment = f" — {t['comment']}" if t["comment"] else ""

            lines.append(
                f"{emoji} {sign}{t['amount']:,.0f}₽ · {cat_emoji} {cat_name}{comment}"
            )
        text = "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=back_to_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery):
    await show_main_menu(callback.message, edit=True)
    await callback.answer("Отменено")