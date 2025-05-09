import logging
from contextlib import asynccontextmanager
from aiosqlite import connect, Error

logger = logging.getLogger(__name__)

class Database:
    _instance = None
    
    def __init__(self):
        self.pool = None
    
    async def connect(self):
        try:
            self.pool = await connect("stellarbot.db")
            await self._init_db()
            logger.info("Database connected")
        except Error as e:
            logger.error(f"Database connection failed: {e}")
            raise

    async def _init_db(self):
        async with self.pool.cursor() as cursor:
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
            
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trans_user 
                ON transactions(user_id)""")
            
            await self.pool.commit()

    @asynccontextmanager
    async def cursor(self):
        async with self.pool.cursor() as cursor:
            try:
                yield cursor
                await self.pool.commit()
            except Exception as e:
                await self.pool.rollback()
                logger.error(f"DB Error: {e}")
                raise
