# config.py
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

class Config:
    # Настройки для Render.com
    RENDER = True
    SERVER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
    
    # Режим работы
    ENV = os.getenv("ENV", "dev").lower()
    IS_PROD = ENV == "production"
    
    # Токены API (обязательные)
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
    FRAGMENT_KEY = os.getenv("FRAGMENT_KEY")  # Для авторизации в Fragment API
    
    # Вебхуки и сервер
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "render_default_secret")
    PORT = int(os.getenv("PORT", 10000))  # Render Free tier требует порт 10000
    WEBHOOK_PATH = "/webhook"
    WEBHOOK_URL = f"{SERVER_URL}{WEBHOOK_PATH}" if SERVER_URL else ""
    
    # Параметры товара
    STAR_PRICE_RUB = 1.6  # Фиксированная цена в продакшене
    MIN_STARS = int(os.getenv("MIN_STARS", 50))  # Новый минимальный лимит
    MAX_STARS = int(os.getenv("MAX_STARS", 1000000))  # Новый максимальный лимит
    
    # URL API сервисов
    CRYPTO_API_URL = "https://pay.crypt.bot/api"
    FRAGMENT_API_URL = "https://api.fragment-api.com/v1/order/stars/"
    
    # Настройки для Render Free Tier
    REQUEST_TIMEOUT = 25  # Максимум 30 сек на запрос
    MAX_CONNECTIONS = 10  # Лимит параллельных соединений
    
    # Администрирование
    ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
    
    # Логирование и мониторинг
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")

    @classmethod
    def validate(cls):
        # Проверка обязательных параметров
        required = {
            "TELEGRAM_TOKEN": cls.TELEGRAM_TOKEN,
            "CRYPTOBOT_TOKEN": cls.CRYPTOBOT_TOKEN,
            "FRAGMENT_KEY": cls.FRAGMENT_KEY
        }
        
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required .env vars: {', '.join(missing)}")

        # Валидация лимитов
        if not (50 <= cls.MIN_STARS < cls.MAX_STARS <= 1_000_000):
            raise ValueError("Invalid stars limits. Must be: 50 ≤ MIN_STARS < MAX_STARS ≤ 1,000,000")

        # Проверки для Render
        if cls.RENDER and not cls.SERVER_URL:
            raise ValueError("RENDER_EXTERNAL_URL must be set in Render.com environment")

    @classmethod
    def render_settings(cls):
        return {
            "auto_start": True,
            "auto_stop": not cls.IS_PROD,  # Для бесплатного аккаунта
            "timeout": cls.REQUEST_TIMEOUT,
            "health_check_path": "/healthz"
        }

    @classmethod
    def database_url(cls):
        return f"sqlite:///{os.getenv('DATABASE_URL', 'stellarbot.db')}"
