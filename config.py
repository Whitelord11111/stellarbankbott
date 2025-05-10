# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Настройки для Render.com
    RENDER = True
    SERVER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
    
    # Режим работы
    ENV = os.getenv("ENV", "dev").lower()
    IS_PROD = ENV == "production"
    
    # Токены API
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
    FRAGMENT_KEY = os.getenv("FRAGMENT_KEY")  # Ключ Fragment API
    
    # Вебхуки и сервер
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "render_default_secret")
    PORT = int(os.getenv("PORT", 10000))
    WEBHOOK_PATH = "/webhook"
    WEBHOOK_URL = f"{SERVER_URL}{WEBHOOK_PATH}" if SERVER_URL else ""
    
    # Параметры товара
    STAR_PRICE_RUB = 1.6
    MIN_STARS = int(os.getenv("MIN_STARS", 50))
    MAX_STARS = int(os.getenv("MAX_STARS", 1000000))
    
    # URL API сервисов
    CRYPTO_API_URL = "https://pay.crypt.bot/api"
    FRAGMENT_API_URL = "https://api.fragment-api.com/v1/order/stars/"
    
    # Настройки для Render
    REQUEST_TIMEOUT = 25
    MAX_CONNECTIONS = 10
    
    # Администрирование
    ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
    
    @classmethod
    def validate(cls):
        required = {
            "TELEGRAM_TOKEN": cls.TELEGRAM_TOKEN,
            "CRYPTOBOT_TOKEN": cls.CRYPTOBOT_TOKEN,
            "FRAGMENT_KEY": cls.FRAGMENT_KEY  # Исправлено имя
        }
        
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required .env vars: {', '.join(missing)}")

        if not (50 <= cls.MIN_STARS < cls.MAX_STARS <= 1_000_000):
            raise ValueError("Invalid stars limits")

        if cls.RENDER and not cls.SERVER_URL:
            raise ValueError("RENDER_EXTERNAL_URL must be set")

    @classmethod
    def render_settings(cls):
        return {
            "auto_start": True,
            "auto_stop": not cls.IS_PROD,
            "timeout": cls.REQUEST_TIMEOUT,
            "health_check_path": "/healthz"
        }
