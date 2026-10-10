import json
import logging
from datetime import datetime

from google import genai
from google.genai import types

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    DEEPSEEK_API_KEY,
)

logger = logging.getLogger(__name__)

# Настраиваем Gemini (новый SDK)
gemini_client = None
if LLM_PROVIDER == "gemini":
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Клиент DeepSeek (на будущее)
deepseek_client = None
if LLM_PROVIDER == "deepseek":
    from openai import AsyncOpenAI
    from config import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    deepseek_client = AsyncOpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
    )


SYSTEM_PROMPT = """Ты — парсер финансовых операций. Пользователь пишет фразу на русском, а ты возвращаешь JSON.

Формат ответа (ТОЛЬКО JSON, без markdown, без пояснений):
{
  "is_transaction": true/false,
  "amount": число или null,
  "type": "income" или "expense" или null,
  "category": "название категории" или null,
  "comment": "краткий комментарий" или null
}

Правила:
- "expense" = расход (потратил, купил, заплатил)
- "income" = доход (получил, заработал, пришло)
- Категории для расходов: Еда, Транспорт, Жильё, Здоровье, Развлечения, Одежда, Связь, Образование, Прочее
- Категории для доходов: Зарплата, Подработка, Подарок, Прочий доход
- Если это не про деньги (просто привет, вопрос и т.д.) — is_transaction: false
- Если сумму не понять — amount: null
- Всегда отвечай ТОЛЬКО валидным JSON

Примеры:
"кофе 300" → {"is_transaction": true, "amount": 300, "type": "expense", "category": "Еда", "comment": "кофе"}
"получил зп 80000" → {"is_transaction": true, "amount": 80000, "type": "income", "category": "Зарплата", "comment": "зарплата"}
"такси до дома 450" → {"is_transaction": true, "amount": 450, "type": "expense", "category": "Транспорт", "comment": "такси"}
"привет" → {"is_transaction": false, "amount": null, "type": null, "category": null, "comment": null}
"""


def _clean_json(raw: str) -> str:
    """Убирает markdown-обёртки вокруг JSON."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    return raw


async def _parse_with_gemini(text: str) -> str:
    """Отправляет текст в Gemini с повторными попытками при 503."""
    import asyncio

    last_error = None
    for attempt in range(3):
        try:
            response = await gemini_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.1,
                ),
            )
            return response.text
        except Exception as e:
            last_error = e
            error_str = str(e)

            # Если это 503 (перегрузка) — ждём и пробуем снова
            if "503" in error_str or "UNAVAILABLE" in error_str:
                wait = 2 ** attempt  # 1, 2, 4 секунды
                logger.warning(
                    f"⚠️ Gemini перегружен, попытка {attempt + 1}/3, "
                    f"жду {wait} сек..."
                )
                await asyncio.sleep(wait)
                continue

            # Другие ошибки — сразу выходим
            raise

    # Если 3 попытки не помогли — бросаем последнюю ошибку
    raise last_error


async def _parse_with_deepseek(text: str) -> str:
    """Отправляет текст в DeepSeek и возвращает сырой ответ."""
    from config import DEEPSEEK_MODEL
    response = await deepseek_client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.1,
        max_tokens=200,
    )
    return response.choices[0].message.content


async def parse_transaction(text: str) -> dict | None:
    """Отправляет текст в ИИ и возвращает распарсенную транзакцию."""
    try:
        if LLM_PROVIDER == "gemini":
            raw = await _parse_with_gemini(text)
        elif LLM_PROVIDER == "deepseek":
            raw = await _parse_with_deepseek(text)
        else:
            raise ValueError(f"Неизвестный провайдер: {LLM_PROVIDER}")

        raw = _clean_json(raw)
        logger.info(f"🤖 {LLM_PROVIDER} ответил: {raw}")

        data = json.loads(raw)

        if not data.get("is_transaction"):
            return None

        if data.get("amount") is None:
            return None

        return data

    except json.JSONDecodeError as e:
        logger.error(f"❌ Не смог распарсить JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка {LLM_PROVIDER}: {e}")
        return None

INSIGHTS_PROMPT = """Ты — финансовый советник. На вход получаешь данные о тратах пользователя за текущий месяц и сравниваешь с прошлым.

Твоя задача: дать 3-4 кратких полезных инсайта на русском.

Формат ответа (ТОЛЬКО JSON, без markdown):
{
  "insights": [
    {"emoji": "📈", "text": "краткий инсайт на 1-2 строки"},
    {"emoji": "🔥", "text": "второй инсайт"},
    {"emoji": "💡", "text": "третий инсайт"}
  ]
}

Правила:
- Пиши дружелюбно, на «ты», без нравоучений
- Используй конкретные цифры и проценты из данных
- Если что-то необычно (траты растут/падают, топ категория изменилась) — выдели это
- Если данных мало (меньше 3 транзакций) — дай 1-2 общих совета по экономии
- Максимум 4 инсайта
- Всегда отвечай ТОЛЬКО валидным JSON

Примеры инсайтов:
"📈 Расходы выросли на 40% к прошлому месяцу — стоит присмотреться"
"🍔 Еда — твоя главная категория, 12 000₽ за месяц (45% всех расходов)"
"📅 Больше всего тратишь в пятницу — 3 500₽"
"💰 Доходы покрывают расходы на 80% — есть запас"
"""


async def generate_insights(summary: dict) -> list[dict] | None:
    """Генерирует ИИ-инсайты на основе данных юзера."""
    import json as _json

    if not summary.get("current"):
        return None

    # Формируем человекочитаемый ввод для ИИ
    cur = summary["current"]
    prev = summary["prev"]
    top_cats = summary.get("top_categories", [])
    top_weekday = summary.get("top_weekday")

    weekday_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

    data_text = f"""
Данные пользователя за текущий месяц:
- Доходы: {cur.get('income', 0)}₽
- Расходы: {cur.get('expense', 0)}₽
- Количество операций: {cur.get('total_count', 0)}

Данные за прошлый месяц:
- Доходы: {prev.get('income', 0)}₽
- Расходы: {prev.get('expense', 0)}₽

Топ-5 категорий расходов текущего месяца:
"""

    for cat in top_cats:
        data_text += f"- {cat.get('category_emoji', '')} {cat.get('category_name', '—')}: {cat.get('total', 0)}₽ ({cat.get('cnt', 0)} операций)\n"

    if top_weekday:
        wd = weekday_names[top_weekday.get("weekday", 0)]
        data_text += f"\nСамый дорогой день недели: {wd} ({top_weekday.get('total', 0)}₽)\n"

    try:
        if LLM_PROVIDER == "gemini":
            # Используем retry-логику
            raw = await _generate_with_gemini(INSIGHTS_PROMPT, data_text)
        else:
            return None

        raw = _clean_json(raw)
        logger.info(f"🤖 Инсайты: {raw}")

        data = _json.loads(raw)
        return data.get("insights", [])

    except Exception as e:
        logger.error(f"❌ Ошибка генерации инсайтов: {e}")
        return None



async def _generate_with_gemini(system_prompt: str, user_content: str) -> str:
    """Универсальный вызов Gemini с retry."""
    import asyncio

    last_error = None
    for attempt in range(3):
        try:
            response = await gemini_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                ),
            )
            return response.text
        except Exception as e:
            last_error = e
            error_str = str(e)

            if "503" in error_str or "UNAVAILABLE" in error_str:
                wait = 2 ** attempt
                logger.warning(f"⚠️ Gemini перегружен (инсайты), попытка {attempt + 1}/3, жду {wait} сек...")
                await asyncio.sleep(wait)
                continue

            raise

    raise last_error

REMINDER_PROMPT = """Ты — парсер даты и времени для напоминаний. Пользователь пишет фразу на русском, а ты возвращаешь JSON.

Формат ответа (ТОЛЬКО JSON, без markdown):
{
  "datetime": "ISO формат YYYY-MM-DDTHH:MM:SS" или null,
  "repeat_type": "none" | "daily" | "weekly" | "monthly"
}

Правила:
- Определи дату и время напоминания из текста
- Используй текущее время пользователя как отправную точку для относительных дат («через час», «завтра»)
- Если время не указано точно (только «завтра») — ставь 09:00
- Если только «вечером» — 19:00
- Если только «утром» — 09:00
- Если только «днём» — 13:00
- Если только «ночью» — 22:00
- repeat_type:
  * "none" — разовое напоминание
  * "daily" — «каждый день», «ежедневно»
  * "weekly" — «каждую неделю», «по понедельникам»
  * "monthly" — «каждый месяц», «каждое 15-е»
- Если дату нельзя понять — datetime: null

Текущее время: {now}

Примеры:
"через 10 минут" → {"datetime": "<now + 10 min>", "repeat_type": "none"}
"завтра в 9:00" → {"datetime": "<tomorrow at 09:00>", "repeat_type": "none"}
"20 декабря в 16:00" → {"datetime": "2026-12-20T16:00:00", "repeat_type": "none"}
"каждый день в 8:00" → {"datetime": "<today or tomorrow at 08:00>", "repeat_type": "daily"}
"каждый понедельник в 10:00" → {"datetime": "<next Monday at 10:00>", "repeat_type": "weekly"}
"каждое 15-е число в 12:00" → {"datetime": "<next 15th at 12:00>", "repeat_type": "monthly"}
"непонятно что" → {"datetime": null, "repeat_type": "none"}
"""


async def parse_reminder_time(text: str) -> dict | None:
    """Парсит дату/время для напоминания через Gemini."""
    import json as _json

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")
    prompt = REMINDER_PROMPT.replace("{now}", now)

    try:
        if LLM_PROVIDER == "gemini":
            raw = await _generate_with_gemini(prompt, text)
        elif LLM_PROVIDER == "deepseek":
            # fallback на deepseek — упрощённая логика
            response = await deepseek_client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.1,
                max_tokens=200,
            )
            raw = response.choices[0].message.content
        else:
            return None

        raw = _clean_json(raw)
        logger.info(f"🤖 Парсинг времени: {raw}")

        data = _json.loads(raw)

        if not data.get("datetime"):
            return None

        return data

    except _json.JSONDecodeError as e:
        logger.error(f"❌ Не смог распарсить JSON времени: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга времени: {e}")
        return None