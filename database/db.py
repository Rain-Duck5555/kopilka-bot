
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


async def get_stats_by_category(user_id: int, type_: str = "expense"):
    """Возвращает суммы по категориям за текущий месяц."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
                c.name AS category_name,
                c.emoji AS category_emoji,
                COALESCE(SUM(t.amount), 0) AS total
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
              AND t.type = ?
              AND strftime('%Y-%m', t.created_at) = strftime('%Y-%m', 'now')
            GROUP BY t.category_id
            ORDER BY total DESC
            """,
            (user_id, type_),
        )
        return await cursor.fetchall()


async def get_last_month_stats(user_id: int, type_: str):
    """Сумма транзакций за прошлый месяц."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE user_id = ?
              AND type = ?
              AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', '-1 month')
            """,
            (user_id, type_),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_user_summary_for_insights(user_id: int):
    """Собирает все данные для ИИ-инсайтов."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Данные за текущий месяц
        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount END), 0) AS income,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount END), 0) AS expense,
                COUNT(*) AS total_count
            FROM transactions
            WHERE user_id = ?
              AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
            """,
            (user_id,),
        )
        current = await cursor.fetchone()

        # Данные за прошлый месяц
        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount END), 0) AS income,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount END), 0) AS expense
            FROM transactions
            WHERE user_id = ?
              AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', '-1 month')
            """,
            (user_id,),
        )
        prev = await cursor.fetchone()

        # Топ-5 категорий расходов за текущий месяц
        cursor = await db.execute(
            """
            SELECT
                c.name AS category_name,
                c.emoji AS category_emoji,
                COALESCE(SUM(t.amount), 0) AS total,
                COUNT(*) AS cnt
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
              AND t.type = 'expense'
              AND strftime('%Y-%m', t.created_at) = strftime('%Y-%m', 'now')
            GROUP BY t.category_id
            ORDER BY total DESC
            LIMIT 5
            """,
            (user_id,),
        )
        top_categories = await cursor.fetchall()

        # Самый дорогой день недели
        cursor = await db.execute(
            """
            SELECT
                CAST(strftime('%w', created_at) AS INTEGER) AS weekday,
                SUM(amount) AS total
            FROM transactions
            WHERE user_id = ?
              AND type = 'expense'
              AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
            GROUP BY weekday
            ORDER BY total DESC
            LIMIT 1
            """,
            (user_id,),
        )
        top_weekday = await cursor.fetchone()

        return {
            "current": dict(current) if current else {},
            "prev": dict(prev) if prev else {},
            "top_categories": [dict(c) for c in top_categories],
            "top_weekday": dict(top_weekday) if top_weekday else None,
        }

async def migrate_db():
    """Добавляет новые поля в существующие таблицы (безопасно)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем, какие поля уже есть в users
        cursor = await db.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in await cursor.fetchall()]

        # Добавляем недостающие поля
        if "is_pro" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN is_pro INTEGER DEFAULT 0")
            print("✅ Добавлено поле: is_pro")

        if "pro_until" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN pro_until TIMESTAMP")
            print("✅ Добавлено поле: pro_until")

        if "operations_this_month" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN operations_this_month INTEGER DEFAULT 0")
            print("✅ Добавлено поле: operations_this_month")

        if "operations_reset_at" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN operations_reset_at TIMESTAMP")
            print("✅ Добавлено поле: operations_reset_at")

        await db.commit()
        print("✅ Миграция БД завершена")

from datetime import datetime, timedelta


async def check_pro_status(user_id: int) -> bool:
    """Проверяет, активна ли Pro-подписка у юзера."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT is_pro, pro_until FROM users WHERE telegram_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()

        if not row:
            return False

        is_pro = row[0]
        pro_until = row[1]

        if not is_pro or not pro_until:
            return False

        # Проверяем, не истёк ли срок
        try:
            pro_until_dt = datetime.fromisoformat(pro_until)
            if pro_until_dt < datetime.now():
                # Подписка истекла — сбрасываем
                await db.execute(
                    "UPDATE users SET is_pro = 0, pro_until = NULL WHERE telegram_id = ?",
                    (user_id,),
                )
                await db.commit()
                return False
            return True
        except (ValueError, TypeError):
            return False


async def can_add_transaction(user_id: int, limit: int = 50) -> tuple[bool, int]:
    """
    Проверяет, может ли юзер добавить операцию.
    Возвращает (можно_ли, осталось_операций).
    """
    # Pro-юзеры без лимита
    if await check_pro_status(user_id):
        return True, 999999

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT operations_this_month, operations_reset_at FROM users WHERE telegram_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()

        if not row:
            return False, 0

        operations = row[0] or 0
        reset_at = row[1]

        # Проверяем, надо ли сбросить счётчик (новый месяц)
        now = datetime.now()
        if not reset_at:
            # Первый раз — ставим дату сброса
            await db.execute(
                "UPDATE users SET operations_reset_at = ? WHERE telegram_id = ?",
                (now.isoformat(), user_id),
            )
            await db.commit()
        else:
            try:
                reset_dt = datetime.fromisoformat(reset_at)
                # Если с даты сброса прошёл месяц или больше — сбрасываем
                if (now - reset_dt).days >= 30:
                    await db.execute(
                        "UPDATE users SET operations_this_month = 0, operations_reset_at = ? WHERE telegram_id = ?",
                        (now.isoformat(), user_id),
                    )
                    await db.commit()
                    operations = 0
            except (ValueError, TypeError):
                pass

        remaining = max(0, limit - operations)
        return operations < limit, remaining


async def increment_operations(user_id: int):
    """Увеличивает счётчик операций на 1."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET operations_this_month = COALESCE(operations_this_month, 0) + 1 WHERE telegram_id = ?",
            (user_id,),
        )
        await db.commit()


async def activate_pro(user_id: int, days: int = 30):
    """Активирует Pro-подписку на N дней."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Если уже Pro — продлеваем от текущей даты
        cursor = await db.execute(
            "SELECT pro_until FROM users WHERE telegram_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()

        now = datetime.now()
        if row and row[0]:
            try:
                current_until = datetime.fromisoformat(row[0])
                if current_until > now:
                    # Продлеваем
                    new_until = current_until + timedelta(days=days)
                else:
                    new_until = now + timedelta(days=days)
            except (ValueError, TypeError):
                new_until = now + timedelta(days=days)
        else:
            new_until = now + timedelta(days=days)

        await db.execute(
            "UPDATE users SET is_pro = 1, pro_until = ? WHERE telegram_id = ?",
            (new_until.isoformat(), user_id),
        )
        await db.commit()