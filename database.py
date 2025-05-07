import sqlite3
from contextlib import contextmanager
from typing import Dict, List

DATABASE_NAME = "stellarbot.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_NAME)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        # Пользователи
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                          user_id INTEGER PRIMARY KEY,
                          username TEXT,
                          total_stars INTEGER DEFAULT 0,
                          total_spent REAL DEFAULT 0
                      )''')
        # Транзакции
        cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
                          tx_id TEXT PRIMARY KEY,
                          user_id INTEGER,
                          stars INTEGER,
                          amount_rub REAL,
                          recipient_tag TEXT,
                          timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                      )''')
        conn.commit()
