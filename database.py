import sqlite3
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)
DATABASE_NAME = "stellarbot.db"

@contextmanager
def db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {str(e)}")
        raise e
    finally:
        conn.close()

def init_db():
    with db_connection() as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                total_stars INTEGER DEFAULT 0,
                total_spent REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица транзакций (исправлено!)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                tx_id TEXT PRIMARY KEY,
                user_id INTEGER REFERENCES users(user_id),
                stars INTEGER NOT NULL,
                amount_rub REAL NOT NULL,
                invoice_id TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL,
                recipient_tag TEXT,  -- Разрешено NULL
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
