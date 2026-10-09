
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database.db import get_user_summary_for_insights
from services.llm import generate_insights
from utils.keyboards import back_to_menu_kb

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "insights")
async def cb_insights(callback: CallbackQuery):
    tg_id = callback.from_user.id

    # Показываем "загрузка"
    await callback.message.edit_text("💡 <b>Анализирую твои траты...</b>\n\nПодожди 3-5 секунд ⏳")

    # Собираем данные
    summary = await get_user_summary_for_insights(tg_id)

    # Проверяем, есть ли данные
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

    # Генерируем инсайты через ИИ
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

    # Формируем сообщение
    lines = ["💡 <b>ИИ-инсайты по твоим тратам</b>\n"]
    for insight in insights:
        emoji = insight.get("emoji", "💡")
        text = insight.get("text", "")
        lines.append(f"{emoji} {text}\n")

    text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb())
    await callback.answer()