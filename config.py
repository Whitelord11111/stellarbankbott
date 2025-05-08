import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]  # Используем строгую проверку
    FRAGMENT_API_KEY = os.environ.get("FRAGMENT_API_KEY", "")
    CRYPTOBOT_TOKEN = os.environ["CRYPTOBOT_TOKEN"]
    WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
    STAR_PRICE_RUB = 1.6
    CRYPTO_API_URL = "https://pay.crypt.bot/api"
