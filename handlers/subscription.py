
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    Message,
    LabeledPrice,
    PreCheckoutQuery,
)

from database.db import check_pro_status, activate_pro
from utils.keyboards import back_to_menu_kb

logger = logging.getLogger(__name__)
router = Router()

# Цена в Stars (≈299₽)
PRO_PRICE_STARS = 299
PRO_DAYS = 30


def subscription_text() -> str:
    """Текст экрана подписки."""
    return (
        "💎 <b>Копилка Pro</b>\n\n"
        "Разблокируй все возможности:\n\n"
        "✅ <b>Безлимитные операции</b>\n"
        "   (в Free — 50 в месяц)\n\n"
        "✅ <b>Аналитика с топ-5 категорий</b>\n"
        "   Узнай, куда уходят деньги\n\n"
        "✅ <b>Сравнение с прошлым месяцем</b>\n"
        "   Следи за динамикой\n\n"
        "✅ <b>ИИ-инсайты</b>\n"
        "   Персональные советы по твоим тратам\n\n"
        "━━━━━━━━━━━━━━━\n"
        f"💰 Цена: <b>{PRO_PRICE_STARS} Stars / месяц</b>\n"
        f"📅 Период: {PRO_DAYS} дней\n"
        "━━━━━━━━━━━━━━━\n\n"
        "👇 Жми кнопку, чтобы оформить"
    )


@router.callback_query(F.data == "subscribe")
async def cb_subscribe(callback: CallbackQuery):
    await callback.message.edit_text(
        subscription_text(),
        reply_markup=subscription_keyboard(),
    )
    await callback.answer()


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    await message.answer(
        subscription_text(),
        reply_markup=subscription_keyboard(),
    )


def subscription_keyboard():
    """Клавиатура экрана подписки."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"💎 Купить за {PRO_PRICE_STARS} Stars",
        callback_data="buy_pro"
    )
    builder.button(text="🏠 В меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "buy_pro")
async def cb_buy_pro(callback: CallbackQuery):
    """Создаём счёт на оплату."""
    await callback.message.answer_invoice(
        title="Копилка Pro",
        description=f"Доступ к Pro-функциям на {PRO_DAYS} дней",
        payload=f"pro_subscription_{PRO_DAYS}d",
        currency="XTR",  # Telegram Stars
        prices=[
            LabeledPrice(label="Копилка Pro", amount=PRO_PRICE_STARS),
        ],
    )
    await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(query: PreCheckoutQuery):
    """Telegram спрашивает: «Списывать?» — подтверждаем."""
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """Оплата прошла — активируем Pro."""
    user_id = message.from_user.id
    payment = message.successful_payment

    logger.info(
        f"💰 Оплата от {user_id}: {payment.total_amount} Stars, "
        f"payload: {payment.invoice_payload}"
    )

    # Активируем Pro
    await activate_pro(user_id, days=PRO_DAYS)

    # Проверяем статус
    is_pro = await check_pro_status(user_id)

    await message.answer(
        "🎉 <b>Спасибо за оплату!</b>\n\n"
        f"💎 Pro-подписка активирована на <b>{PRO_DAYS} дней</b>.\n\n"
        "Теперь тебе доступно:\n"
        "• Безлимитные операции\n"
        "• Аналитика с топ-5 категорий\n"
        "• Сравнение с прошлым месяцем\n"
        "• ИИ-инсайты\n\n"
        f"✅ Статус Pro: <b>{'активен' if is_pro else 'ошибка'}</b>\n\n"
        "Приятного использования! 🚀",
        reply_markup=back_to_menu_kb(),
    )