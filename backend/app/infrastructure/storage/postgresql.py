import os
import logging
import asyncpg
from typing import Optional
from functools import lru_cache

logger = logging.getLogger(__name__)


class PostgreSQL:
    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._database_url = os.environ.get('DATABASE_URL')

    async def initialize(self) -> None:
        if self._pool is not None:
            return

        try:
            self._pool = await asyncpg.create_pool(
                self._database_url,
                min_size=2,
                max_size=10,
            )
            logger.info("Successfully connected to PostgreSQL")

            async with self._pool.acquire() as conn:
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id VARCHAR(64) PRIMARY KEY,
                        fullname VARCHAR(255) NOT NULL,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        password_hash VARCHAR(512),
                        role VARCHAR(20) DEFAULT 'user',
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        last_login_at TIMESTAMPTZ
                    )
                ''')
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS agents (
                        agent_id VARCHAR(64) PRIMARY KEY,
                        model_name VARCHAR(255),
                        temperature FLOAT DEFAULT 0.7,
                        max_tokens INTEGER DEFAULT 2000,
                        memories JSONB DEFAULT '{}',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                ''')
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id VARCHAR(64) PRIMARY KEY,
                        user_id VARCHAR(64) NOT NULL,
                        sandbox_id VARCHAR(255),
                        agent_id VARCHAR(64) NOT NULL,
                        task_id VARCHAR(255),
                        title VARCHAR(500),
                        unread_message_count INTEGER DEFAULT 0,
                        latest_message TEXT,
                        latest_message_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        events JSONB DEFAULT '[]',
                        status VARCHAR(20) DEFAULT 'pending',
                        files JSONB DEFAULT '[]',
                        is_shared BOOLEAN DEFAULT FALSE
                    )
                ''')
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS uploaded_files (
                        file_id VARCHAR(64) PRIMARY KEY,
                        filename VARCHAR(500) NOT NULL,
                        file_path VARCHAR(1000),
                        content_type VARCHAR(255),
                        file_size BIGINT DEFAULT 0,
                        upload_date TIMESTAMPTZ DEFAULT NOW(),
                        metadata JSONB,
                        user_id VARCHAR(64) NOT NULL,
                        file_data BYTEA
                    )
                ''')
            logger.info("All PostgreSQL tables created successfully")

        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL: {str(e)}")
            raise

    async def shutdown(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("Disconnected from PostgreSQL")
        get_postgresql.cache_clear()

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("PostgreSQL pool not initialized. Call initialize() first.")
        return self._pool


@lru_cache()
def get_postgresql() -> PostgreSQL:
    return PostgreSQL()
