
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database.db import (
    get_month_stats,
    get_last_month_stats,
    get_stats_by_category,
)
from utils.keyboards import back_to_menu_kb

logger = logging.getLogger(__name__)
router = Router()


def _format_delta(current: float, previous: float) -> str:
    """Форматирует изменение в процентах."""
    if previous == 0:
        if current == 0:
            return "—"
        return "🆕 первая активность"

    diff = ((current - previous) / previous) * 100
    arrow = "📈" if diff > 0 else "📉"
    sign = "+" if diff > 0 else ""
    return f"{arrow} {sign}{diff:.0f}% к прошлому месяцу"


@router.callback_query(F.data == "analytics")
async def cb_analytics(callback: CallbackQuery):
    tg_id = callback.from_user.id

    # Текущий месяц
    income = await get_month_stats(tg_id, "income")
    expense = await get_month_stats(tg_id, "expense")

    # Прошлый месяц
    prev_income = await get_last_month_stats(tg_id, "income")
    prev_expense = await get_last_month_stats(tg_id, "expense")

    # По категориям (только расходы, топ-5)
    categories = await get_stats_by_category(tg_id, "expense")

    lines = ["📊 <b>Аналитика за месяц</b>\n"]

    # Общие суммы
    lines.append(f"💰 Доходы: <b>{income:,.0f}₽</b>")
    lines.append(f"   {_format_delta(income, prev_income)}")
    lines.append("")

    lines.append(f"💸 Расходы: <b>{expense:,.0f}₽</b>")
    lines.append(f"   {_format_delta(expense, prev_expense)}")
    lines.append("")

    # Баланс
    balance = income - expense
    balance_emoji = "✅" if balance >= 0 else "⚠️"
    lines.append(f"{balance_emoji} Баланс: <b>{balance:,.0f}₽</b>")
    lines.append("")

    # Топ-5 категорий
    if categories:
        lines.append("🏆 <b>Топ-5 категорий расходов:</b>")
        for i, cat in enumerate(categories[:5], 1):
            emoji = cat["category_emoji"] or "📁"
            name = cat["category_name"] or "—"
            total = cat["total"]
            percent = (total / expense * 100) if expense > 0 else 0
            lines.append(f"{i}. {emoji} {name} — <b>{total:,.0f}₽</b> ({percent:.0f}%)")
    else:
        lines.append("📭 <i>Пока нет расходов за этот месяц</i>")

    text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb())
    await callback.answer()