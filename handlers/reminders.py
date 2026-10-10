
import logging
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import (
    add_reminder,
    get_user_reminders,
    count_user_reminders,
    delete_reminder,
    get_pending_reminders,
    reschedule_reminder,
    mark_reminder_sent,
    check_pro_status,
)
from services.llm import parse_reminder_time
from utils.keyboards import main_menu_kb, cancel_kb, back_to_menu_kb

logger = logging.getLogger(__name__)
router = Router()

FREE_LIMIT = 5


class AddReminder(StatesGroup):
    waiting_text = State()
    waiting_time = State()


# ============ ГЛАВНЫЙ ЭКРАН ============

def reminders_kb():
    """Клавиатура экрана напоминаний."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать напоминание", callback_data="remind_new")
    builder.button(text="📋 Мои напоминания", callback_data="remind_list")
    builder.button(text="🏠 В меню", callback_data="main_menu")
    builder.adjust(1, 1, 1)
    return builder.as_markup()


@router.callback_query(F.data == "reminders")
async def cb_reminders(callback: CallbackQuery):
    tg_id = callback.from_user.id
    is_pro = await check_pro_status(tg_id)
    count = await count_user_reminders(tg_id)

    if is_pro:
        limit_text = "💎 <b>Pro:</b> безлимит"
    else:
        limit_text = f"📊 <b>Использовано:</b> {count} / {FREE_LIMIT}"

    text = (
        "🔔 <b>Напоминания</b>\n\n"
        "Я могу напомнить о чём угодно:\n"
        "• 📞 Позвонить маме\n"
        "• 💊 Выпить витамины\n"
        "• 🎂 Поздравить друга\n"
        "• 💰 Оплатить кредит\n\n"
        f"{limit_text}"
    )

    await callback.message.edit_text(text, reply_markup=reminders_kb())
    await callback.answer()


# ============ СОЗДАНИЕ ============

@router.callback_query(F.data == "remind_new")
async def cb_remind_new(callback: CallbackQuery, state: FSMContext):
    tg_id = callback.from_user.id
    count = await count_user_reminders(tg_id)
    is_pro = await check_pro_status(tg_id)

    if not is_pro and count >= FREE_LIMIT:
        await callback.message.edit_text(
            "🔒 <b>Лимит напоминаний исчерпан</b>\n\n"
            f"В бесплатном тарифе доступно <b>{FREE_LIMIT} напоминаний</b>.\n\n"
            "💎 Оформи <b>Pro-подписку за 299₽/мес</b>, и получишь:\n"
            "• Неограниченные напоминания\n"
            "• Повторяющиеся (каждый день/неделю/месяц)\n"
            "• Безлимит операций\n"
            "• Аналитику и ИИ-инсайты\n\n"
            "Команда: /subscribe",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return

    await state.set_state(AddReminder.waiting_text)
    await callback.message.edit_text(
        "🔔 <b>Новое напоминание</b>\n\n"
        "Напиши, о чём напомнить:\n\n"
        "Например:\n"
        "• <i>Позвонить маме</i>\n"
        "• <i>Купить хлеб</i>\n"
        "• <i>Оплатить кредит</i>",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(AddReminder.waiting_text)
async def process_reminder_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if not text or len(text) > 200:
        await message.answer(
            "❌ Текст должен быть от 1 до 200 символов. Попробуй ещё раз:",
            reply_markup=cancel_kb()
        )
        return

    await state.update_data(text=text)
    await state.set_state(AddReminder.waiting_time)

    await message.answer(
        f"📝 Запомнил: <i>{text}</i>\n\n"
        "🕐 Теперь напиши, <b>когда напомнить</b>:\n\n"
        "Примеры:\n"
        "• <i>через 10 минут</i>\n"
        "• <i>через час</i>\n"
        "• <i>завтра в 9:00</i>\n"
        "• <i>20 декабря в 16:00</i>\n"
        "• <i>каждый день в 8:00</i>",
        reply_markup=cancel_kb()
    )


@router.message(AddReminder.waiting_time)
async def process_reminder_time(message: Message, state: FSMContext):
    text_input = (message.text or "").strip()

    if not text_input:
        await message.answer("❌ Напиши время, например: <i>завтра в 9:00</i>")
        return

    # Отправляем "печатает"
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Парсим через ИИ
    parsed = await parse_reminder_time(text_input)

    if not parsed or not parsed.get("datetime"):
        await message.answer(
            "🤔 Не понял дату и время.\n\n"
            "Попробуй так:\n"
            "• <i>через 10 минут</i>\n"
            "• <i>завтра в 9:00</i>\n"
            "• <i>20 декабря в 16:00</i>",
            reply_markup=cancel_kb()
        )
        return

    data = await state.get_data()
    reminder_text = data["text"]

    # Проверяем, что время в будущем
    try:
        remind_dt = datetime.fromisoformat(parsed["datetime"])
    except (ValueError, TypeError):
        await message.answer("❌ Ошибка в дате. Попробуй ещё раз:")
        return

    if remind_dt <= datetime.now():
        await message.answer(
            "❌ Это время уже прошло. Напиши будущее время:",
            reply_markup=cancel_kb()
        )
        return

    # Проверяем повтор
    repeat_type = parsed.get("repeat_type", "none")
    if repeat_type != "none":
        # Повторы только для Pro
        is_pro = await check_pro_status(message.from_user.id)
        if not is_pro:
            await message.answer(
                "🔒 <b>Повторяющиеся напоминания — только в Pro</b>\n\n"
                "💎 Оформи Pro за 299₽/мес, чтобы напоминания\n"
                "повторялись каждый день / неделю / месяц.\n\n"
                "Команда: /subscribe",
                reply_markup=back_to_menu_kb()
            )
            await state.clear()
            return

    # Сохраняем
    await add_reminder(
        user_id=message.from_user.id,
        text=reminder_text,
        remind_at=remind_dt.isoformat(),
        repeat_type=repeat_type,
    )

    await state.clear()

    # Форматируем красиво
    date_str = remind_dt.strftime("%d.%m.%Y в %H:%M")

    repeat_text = ""
    if repeat_type == "daily":
        repeat_text = "\n🔁 Повтор: <b>каждый день</b>"
    elif repeat_type == "weekly":
        repeat_text = "\n🔁 Повтор: <b>каждую неделю</b>"
    elif repeat_type == "monthly":
        repeat_text = "\n🔁 Повтор: <b>каждый месяц</b>"

    await message.answer(
        f"✅ <b>Напоминание создано!</b>\n\n"
        f"📝 {reminder_text}\n"
        f"🕐 {date_str}{repeat_text}",
        reply_markup=back_to_menu_kb()
    )


# ============ СПИСОК ============

@router.callback_query(F.data == "remind_list")
async def cb_remind_list(callback: CallbackQuery):
    tg_id = callback.from_user.id
    reminders = await get_user_reminders(tg_id)

    if not reminders:
        await callback.message.edit_text(
            "📋 <b>У тебя пока нет напоминаний</b>\n\n"
            "Создай первое — жми «➕ Создать напоминание».",
            reply_markup=reminders_kb()
        )
        await callback.answer()
        return

    lines = ["📋 <b>Твои напоминания:</b>\n"]
    builder = InlineKeyboardBuilder()

    for r in reminders:
        try:
            dt = datetime.fromisoformat(r["remind_at"])
            date_str = dt.strftime("%d.%m.%Y %H:%M")
        except (ValueError, TypeError):
            date_str = "—"

        repeat = ""
        if r["repeat_type"] == "daily":
            repeat = " 🔁"
        elif r["repeat_type"] == "weekly":
            repeat = " 🔁"
        elif r["repeat_type"] == "monthly":
            repeat = " 🔁"

        lines.append(f"• {r['text']}{repeat}\n  🕐 {date_str}\n")

        # Кнопка удаления для каждого
        builder.button(
            text=f"❌ Удалить: {r['text'][:20]}...",
            callback_data=f"remind_delete:{r['id']}"
        )

    builder.button(text="🏠 В меню", callback_data="main_menu")
    builder.adjust(1)

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=builder.as_markup()
    )
    await callback.answer()


# ============ УДАЛЕНИЕ ============

@router.callback_query(F.data.startswith("remind_delete:"))
async def cb_remind_delete(callback: CallbackQuery):
    reminder_id = int(callback.data.split(":")[1])
    success = await delete_reminder(reminder_id, callback.from_user.id)

    if success:
        await callback.answer("✅ Удалено")
    else:
        await callback.answer("❌ Не найдено")

    # Обновляем список
    await cb_remind_list(callback)


# ============ ОТЛОЖИТЬ / ГОТОВО ============

@router.callback_query(F.data.startswith("remind_snooze:"))
async def cb_remind_snooze(callback: CallbackQuery):
    parts = callback.data.split(":")
    minutes = int(parts[1])
    reminder_id = int(parts[2])

    new_time = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    await reschedule_reminder(reminder_id, new_time)

    await callback.message.edit_text(
        f"⏰ <b>Отложено на {minutes} минут</b>\n\n"
        f"Напомню снова в {datetime.now().strftime('%H:%M')} + {minutes} мин."
    )
    await callback.answer("⏰ Отложено")


@router.callback_query(F.data.startswith("remind_done:"))
async def cb_remind_done(callback: CallbackQuery):
    reminder_id = int(callback.data.split(":")[1])
    await mark_reminder_sent(reminder_id)

    await callback.message.edit_text("✅ <b>Отлично! Напоминание выполнено.</b>")
    await callback.answer("✅ Готово")