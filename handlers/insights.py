import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import get_user_summary_for_insights, check_pro_status
from services.llm import generate_insights
from utils.keyboards import back_to_menu_kb

logger = logging.getLogger(__name__)
router = Router()


def _preview_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для превью (не Pro)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="💎 Купить Pro — 299₽/мес", callback_data="subscribe")
    builder.button(text="🏠 В меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "insights")
async def cb_insights(callback: CallbackQuery):
    tg_id = callback.from_user.id

    # Проверяем Pro
    is_pro = await check_pro_status(tg_id)

    if not is_pro:
        # Превью для Free-юзеров
        text = (
            "🔒 <b>ИИ-инсайты — только в Pro</b>\n\n"
            "Что такое ИИ-инсайты?\n\n"
            "Это <b>персональные советы</b> от ИИ на основе твоих трат:\n\n"
            "📈 <i>«Ты тратишь на 🍔 Еду на 40% больше, чем в прошлом месяце»</i>\n\n"
            "📅 <i>«Больше всего ты тратишь по пятницам»</i>\n\n"
            "💡 <i>«Расходы растут — стоит присмотреться»</i>\n\n"
            "━━━━━━━━━━━━━━━\n"
            "💎 Оформи Pro за <b>299₽/мес</b> — и получишь:\n"
            "• ИИ-инсайты\n"
            "• Полную аналитику\n"
            "• Безлимит операций\n\n"
            "👇 Жми, чтобы оформить"
        )

        await callback.message.edit_text(text, reply_markup=_preview_keyboard())
        await callback.answer()
        return

    # Генерация инсайтов — для Pro
    await callback.message.edit_text("💡 <b>Анализирую твои траты...</b>\n\nПодожди 3-5 секунд ⏳")

    summary = await get_user_summary_for_insights(tg_id)

    if not summary.get("current") or summary["current"].get("total_count", 0) < 3:
        await callback.message.edit_text(
            "💡 <b>ИИ-инсайты</b>\n\n"
            "📭 Пока мало данных для анализа.\n\n"
            "Добавь минимум <b>3 операции</b> за этот месяц — "
            "и я дам полезные советы по твоим тратам.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return

    insights = await generate_insights(summary)

    if not insights:
        await callback.message.edit_text(
            "💡 <b>ИИ-инсайты</b>\n\n"
            "⚠️ Не удалось сгенерировать инсайты (ИИ временно недоступен).\n\n"
            "Попробуй ещё раз через минуту.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return

    lines = ["💡 <b>ИИ-инсайты по твоим тратам</b>\n"]
    for insight in insights:
        emoji = insight.get("emoji", "💡")
        text = insight.get("text", "")
        lines.append(f"{emoji} {text}\n")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=back_to_menu_kb()
    )
    await callback.answer()