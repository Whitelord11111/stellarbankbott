# database.py
import sqlite3
import logging
from contextlib import asynccontextmanager
from aiosqlite import connect

logger = logging.getLogger(__name__)

class Database:
    _instance = None
    
    def __init__(self):
        self.conn = None
    
    async def connect(self):
        self.conn = await connect(
            "stellarbot.db",
            row_factory=sqlite3.Row  # Добавляем row factory
        )
        await self._init_db()
        logger.info("Database connected")

    async def _init_db(self):
        async with self.conn.cursor() as cursor:
            # Создание таблиц
            await cursor.execute("PRAGMA foreign_keys = ON")
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    total_stars INTEGER DEFAULT 0,
                    total_spent REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""")
            
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    tx_id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(user_id),
                    stars INTEGER NOT NULL,
                    amount_rub REAL NOT NULL,
                    invoice_id TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('created', 'paid', 'completed', 'refunded')),
                    recipient_tag TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""")
            
            # Индексы
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trans_user 
                ON transactions(user_id)""")
            
            await self.conn.commit()

    @asynccontextmanager
    async def cursor(self):
        async with self.conn.cursor() as cursor:
            try:
                yield cursor
                await self.conn.commit()
            except Exception as e:
                await self.conn.rollback()
                logger.error(f"DB Error: {e}")
                raise
