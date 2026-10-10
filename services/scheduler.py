
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import (
    get_pending_reminders,
    mark_reminder_sent,
    reschedule_reminder,
)

logger = logging.getLogger(__name__)


def reminder_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    """Кнопки под напоминанием."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏰ +10 минут", callback_data=f"remind_snooze:10:{reminder_id}")
    builder.button(text="⏰ +1 час", callback_data=f"remind_snooze:60:{reminder_id}")
    builder.button(text="✅ Готово", callback_data=f"remind_done:{reminder_id}")
    builder.adjust(2, 1)
    return builder.as_markup()


async def check_reminders(bot: Bot):
    """Проверяет и отправляет напоминания, время которых пришло."""
    try:
        reminders = await get_pending_reminders()

        for reminder in reminders:
            user_id = reminder["user_id"]
            text = reminder["text"]
            repeat_type = reminder["repeat_type"] or "none"
            reminder_id = reminder["id"]

            # Отправляем напоминание
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🔔 <b>Напоминание!</b>\n\n"
                        f"📝 {text}"
                    ),
                    reply_markup=reminder_keyboard(reminder_id),
                )
                logger.info(f"🔔 Отправлено напоминание #{reminder_id} юзеру {user_id}")

            except Exception as e:
                logger.error(f"❌ Не смог отправить напоминание #{reminder_id}: {e}")
                # Всё равно помечаем отправленным, чтобы не зацикливаться
                await mark_reminder_sent(reminder_id)
                continue

            # Обработка повторов
            if repeat_type == "none":
                # Разовое — помечаем отправленным
                await mark_reminder_sent(reminder_id)

            elif repeat_type == "daily":
                # Следующее срабатывание — через день
                old_dt = datetime.fromisoformat(reminder["remind_at"])
                new_dt = old_dt + timedelta(days=1)
                await reschedule_reminder(reminder_id, new_dt.isoformat())

            elif repeat_type == "weekly":
                # Через неделю
                old_dt = datetime.fromisoformat(reminder["remind_at"])
                new_dt = old_dt + timedelta(weeks=1)
                await reschedule_reminder(reminder_id, new_dt.isoformat())

            elif repeat_type == "monthly":
                # Через месяц (30 дней для простоты)
                old_dt = datetime.fromisoformat(reminder["remind_at"])
                new_dt = old_dt + timedelta(days=30)
                await reschedule_reminder(reminder_id, new_dt.isoformat())

    except Exception as e:
        logger.error(f"❌ Ошибка в планировщике: {e}")


async def scheduler_loop(bot: Bot):
    """Бесконечный цикл — каждую минуту проверяет напоминания."""
    logger.info("🕐 Планировщик запущен (проверка каждую минуту)")

    while True:
        try:
            await check_reminders(bot)
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле планировщика: {e}")

        # Ждём 60 секунд
        await asyncio.sleep(60)