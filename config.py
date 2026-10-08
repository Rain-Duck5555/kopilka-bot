import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# Токен бота от @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Ключи ИИ-провайдеров
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Какой провайдер используем: "gemini" или "deepseek"
LLM_PROVIDER = "gemini"

# Модель Gemini (бесплатная Flash)
GEMINI_MODEL = "gemini-3.8-flash"

# Путь к базе данных
DB_PATH = "moneybot.db"

# Проверка секретов
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env файле")

if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY не найден в .env файле")

if LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEY:
    raise ValueError("❌ DEEPSEEK_API_KEY не найден в .env файле")

print("✅ Конфиг загружен успешно")