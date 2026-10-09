import json
import logging

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