import sqlite3
from contextlib import contextmanager

DATABASE_NAME = "stellarbot.db"

@contextmanager
def db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    with db_connection() as conn:
        cursor = conn.cursor()
        
        # Создание таблицы пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                total_stars INTEGER DEFAULT 0,
                total_spent REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
# Измените схему таблицы transactions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                tx_id TEXT PRIMARY KEY,
                user_id INTEGER,
                stars INTEGER,
                amount_rub REAL,
                recipient_tag TEXT DEFAULT '',  # Разрешены пустые значения
                invoice_id TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
