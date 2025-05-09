# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Основные настройки среды
    ENV = os.getenv("ENV", "dev").lower()
    IS_PROD = ENV == "production"
    
    # Токены API
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
    FRAGMENT_API_KEY = os.getenv("FRAGMENT_API_KEY")
    FRAGMENT_KEY = os.getenv("FRAGMENT_KEY")  # Для авторизации в Fragment API
    
    # Настройки вебхуков
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-domain.com/webhook")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default_secret_token")
    PORT = int(os.getenv("PORT", 10000))
    
    # Параметры товара
    STAR_PRICE_RUB = 1.6 if IS_PROD else 0.01  # Цена за 1 звезду
    MIN_STARS = int(os.getenv("MIN_STARS", 50))  # Минимальное количество для покупки
    MAX_STARS = int(os.getenv("MAX_STARS", 1000000))  # Максимальное количество
    
    # URL API сервисов
    CRYPTO_API_URL = "https://pay.crypt.bot/api"
    FRAGMENT_API_URL = "https://api.fragment-api.com/v1/order/stars/"
    
    # Администрирование
    ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
    
    # Настройки базы данных
    DATABASE_NAME = os.getenv("DATABASE_NAME", "stellarbot.db")
    DB_BACKUP_DIR = os.getenv("DB_BACKUP_DIR", "backups")

    @classmethod
    def validate(cls):
        required_credentials = {
            "TELEGRAM_TOKEN": cls.TELEGRAM_TOKEN,
            "CRYPTOBOT_TOKEN": cls.CRYPTOBOT_TOKEN,
            "FRAGMENT_API_KEY": cls.FRAGMENT_API_KEY,
            "FRAGMENT_KEY": cls.FRAGMENT_KEY
        }
        
        missing = [name for name, value in required_credentials.items() if not value]
        if missing:
            raise ValueError(f"Отсутствуют обязательные параметры в .env: {', '.join(missing)}")

        if not cls.MIN_STARS < cls.MAX_STARS:
            raise ValueError("MIN_STARS должен быть меньше MAX_STARS")

        if cls.STAR_PRICE_RUB <= 0:
            raise ValueError("Цена звезды должна быть положительной")

    @classmethod
    def get_db_backup_path(cls):
        return os.path.join(cls.DB_BACKUP_DIR, f"backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db")
