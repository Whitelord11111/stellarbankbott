# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
    FRAGMENT_KEY = os.getenv("FRAGMENT_KEY")
    WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL") + "/webhook"
    STAR_PRICE_USD = 0.02  # Новая цена в USD вместо RUB
    MIN_STARS = 50
    MAX_STARS = 1000000
    ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
