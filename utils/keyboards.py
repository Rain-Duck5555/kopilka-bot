
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить трату", callback_data="add_expense")
    builder.button(text="💰 Добавить доход", callback_data="add_income")
    builder.button(text="📊 Статистика", callback_data="stats")
    builder.button(text="📈 Аналитика", callback_data="analytics")
    builder.button(text="💡 Инсайты", callback_data="insights")
    builder.button(text="📜 История", callback_data="history")
    builder.button(text="💎 Подписка Pro", callback_data="subscribe")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def categories_kb(categories: list, type_: str) -> InlineKeyboardMarkup:
    """Клавиатура с категориями."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(
            text=f"{cat['emoji']} {cat['name']}",
            callback_data=f"cat:{type_}:{cat['id']}"
        )
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    """Кнопка отмены."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    """Кнопка назад в меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 В меню", callback_data="main_menu")
    return builder.as_markup()