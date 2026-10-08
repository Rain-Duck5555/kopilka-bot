
import aiosqlite
from config import DB_PATH


# SQL-запросы для создания таблиц
CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_pro INTEGER DEFAULT 0,
    pro_until TIMESTAMP
);
"""

CREATE_CATEGORIES = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    emoji TEXT DEFAULT '📁',
    type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
    user_id INTEGER,
    is_default INTEGER DEFAULT 0
);
"""

CREATE_TRANSACTIONS = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
    category_id INTEGER,
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(telegram_id),
    FOREIGN KEY (category_id) REFERENCES categories(id)
);
"""


# Дефолтные категории (общие для всех)
DEFAULT_CATEGORIES = [
    # Расходы
    ("Еда", "🍔", "expense"),
    ("Транспорт", "🚕", "expense"),
    ("Жильё", "🏠", "expense"),
    ("Здоровье", "💊", "expense"),
    ("Развлечения", "🎮", "expense"),
    ("Одежда", "👕", "expense"),
    ("Связь", "📱", "expense"),
    ("Образование", "📚", "expense"),
    ("Прочее", "📁", "expense"),
    # Доходы
    ("Зарплата", "💼", "income"),
    ("Подработка", "💻", "income"),
    ("Подарок", "🎁", "income"),
    ("Прочий доход", "💰", "income"),
]


async def init_db():
    """Создаёт все таблицы и добавляет дефолтные категории."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_USERS)
        await db.execute(CREATE_CATEGORIES)
        await db.execute(CREATE_TRANSACTIONS)

        # Проверяем, есть ли дефолтные категории
        cursor = await db.execute(
            "SELECT COUNT(*) FROM categories WHERE is_default = 1"
        )
        row = await cursor.fetchone()

        if row[0] == 0:
            # Добавляем дефолтные категории
            await db.executemany(
                "INSERT INTO categories (name, emoji, type, is_default) VALUES (?, ?, ?, 1)",
                DEFAULT_CATEGORIES
            )
            print("✅ Дефолтные категории добавлены")

        await db.commit()
        print("✅ База данных инициализирована")


async def get_user(telegram_id: int):
    """Возвращает юзера или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        return await cursor.fetchone()


async def create_user(telegram_id: int, username: str, first_name: str):
    """Создаёт нового юзера."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (telegram_id, username, first_name)
        )
        await db.commit()


async def get_categories(user_id: int, type_: str = None):
    """Возвращает категории для юзера (дефолтные + его собственные)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM categories WHERE (user_id IS NULL OR user_id = ?)"
        params = [user_id]

        if type_:
            query += " AND type = ?"
            params.append(type_)

        query += " ORDER BY is_default DESC, id ASC"
        cursor = await db.execute(query, params)
        return await cursor.fetchall()

async def get_category_by_name(user_id: int, name: str, type_: str):
    """Находит категорию по имени и типу."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM categories
            WHERE (user_id IS NULL OR user_id = ?)
              AND name = ?
              AND type = ?
            LIMIT 1
            """,
            (user_id, name, type_),
        )
        return await cursor.fetchone()


async def add_transaction(
    user_id: int,
    amount: float,
    type_: str,
    category_id: int | None,
    comment: str | None,
):
    """Добавляет транзакцию."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO transactions (user_id, amount, type, category_id, comment)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, amount, type_, category_id, comment),
        )
        await db.commit()


async def get_month_stats(user_id: int, type_: str):
    """Сумма транзакций за текущий месяц по типу."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE user_id = ?
              AND type = ?
              AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
            """,
            (user_id, type_),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_last_transactions(user_id: int, limit: int = 10):
    """Возвращает последние N транзакций юзера."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT t.*, c.name AS category_name, c.emoji AS category_emoji
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
            ORDER BY t.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return await cursor.fetchall()


async def delete_last_transaction(user_id: int):
    """Удаляет последнюю транзакцию юзера."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            DELETE FROM transactions
            WHERE id = (
                SELECT id FROM transactions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            )
            """,
            (user_id,),
        )
        await db.commit()
        return cursor.rowcount > 0