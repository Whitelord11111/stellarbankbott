import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Обязательные переменные
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or ""
    CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN") or ""
    
    # Опциональные переменные
    FRAGMENT_API_KEY = os.getenv("FRAGMENT_API_KEY", "")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
    
    # Настройки вебхука
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://stellarbankbot.onrender.com/webhook")
    CRYPTO_API_URL = "https://pay.crypt.bot/api"
    
    # Цены
    STAR_PRICE_RUB = 1.6  # 1.6 рубля за 1 звезду
    
    @classmethod
    def validate(cls):
        """Проверка обязательных настроек"""
        if not cls.TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_TOKEN не задан в .env")
        if not cls.CRYPTOBOT_TOKEN:
            raise ValueError("CRYPTOBOT_TOKEN не задан в .env")
