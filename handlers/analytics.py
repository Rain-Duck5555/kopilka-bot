import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import (
    get_month_stats,
    get_last_month_stats,
    get_stats_by_category,
    check_pro_status,
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


def _preview_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для превью (не Pro)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="💎 Купить Pro — 299₽/мес", callback_data="subscribe")
    builder.button(text="🏠 В меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "analytics")
async def cb_analytics(callback: CallbackQuery):
    tg_id = callback.from_user.id

    # Проверяем Pro
    is_pro = await check_pro_status(tg_id)

    # Данные для превью (доступны всем)
    categories = await get_stats_by_category(tg_id, "expense")

    if not is_pro:
        # Превью для Free-юзеров
        lines = [
            "🔒 <b>Аналитика — только в Pro</b>\n",
            "Вот <b>превью</b> того, что ты упускаешь:\n",
        ]

        if categories:
            lines.append(f"📊 У тебя <b>{len(categories)}</b> категорий расходов")
            top = categories[0]
            emoji = top["category_emoji"] or "📁"
            name = top["category_name"] or "—"
            lines.append(f"🔝 Топ: {emoji} <b>{name}</b> — {top['total']:,.0f}₽")
        else:
            lines.append("📭 Пока нет расходов за этот месяц")

        lines.append("")
        lines.append("💎 <b>В Pro-версии доступно:</b>")
        lines.append("• Полная аналитика с топ-5 категорий")
        lines.append("• Сравнение с прошлым месяцем")
        lines.append("• Проценты по каждой категории")
        lines.append("• ИИ-инсайты по тратам")
        lines.append("")
        lines.append("Оформи Pro за <b>299₽/мес</b> 👇")

        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=_preview_keyboard()
        )
        await callback.answer()
        return

    # Полная аналитика — для Pro
    income = await get_month_stats(tg_id, "income")
    expense = await get_month_stats(tg_id, "expense")
    prev_income = await get_last_month_stats(tg_id, "income")
    prev_expense = await get_last_month_stats(tg_id, "expense")

    lines = ["📊 <b>Аналитика за месяц</b>\n"]

    lines.append(f"💰 Доходы: <b>{income:,.0f}₽</b>")
    lines.append(f"   {_format_delta(income, prev_income)}")
    lines.append("")

    lines.append(f"💸 Расходы: <b>{expense:,.0f}₽</b>")
    lines.append(f"   {_format_delta(expense, prev_expense)}")
    lines.append("")

    balance = income - expense
    balance_emoji = "✅" if balance >= 0 else "⚠️"
    lines.append(f"{balance_emoji} Баланс: <b>{balance:,.0f}₽</b>")
    lines.append("")

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

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=back_to_menu_kb()
    )
    await callback.answer()