import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    FRAGMENT_API_KEY = os.getenv("FRAGMENT_API_KEY")
    CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
    STAR_PRICE_RUB = 1.6
    CRYPTO_API_URL = "https://pay.crypt.bot/api"
