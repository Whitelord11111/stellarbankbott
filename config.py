import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Webhook
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# CryptoBot
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
CRYPTO_PATH = os.getenv("CRYPTO_PATH", "/crypto")
CRYPTO_WEBHOOK_URL = f"{WEBHOOK_HOST}{CRYPTO_PATH}"

# Fragment
FRAGMENT_API_KEY = os.getenv("FRAGMENT_API_KEY")

# Server
PORT = int(os.getenv("PORT", 8080))

