import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Переименовано BOT_TOKEN -> TELEGRAM_TOKEN (для aiogram)
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or ""
    CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN") or ""
    FRAGMENT_API_KEY = os.getenv("FRAGMENT_API_KEY", "")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default_secret")  # Добавлено
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://stellarbankbot.onrender.com/webhook")
    CRYPTO_API_URL = "https://pay.crypt.bot/api"
    STAR_PRICE_RUB = 1.6
    PORT = int(os.getenv("PORT", 10000))
    FRAGMENT_API_URL = "https://api.fragment-api.com/v1/order/stars/"
    FRAGMENT_KEY = os.getenv("FRAGMENT_KEY", "")
    
    @classmethod
    def validate(cls):
        if not cls.TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_TOKEN не задан в .env")
        if not cls.CRYPTOBOT_TOKEN:
            raise ValueError("CRYPTOBOT_TOKEN не задан")
