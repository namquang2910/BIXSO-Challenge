"""
Database configuration, schema initialization, and session management.
Uses SQLAlchemy async engine with PostgreSQL.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for DB sessions."""
    async with get_db_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Schema DDL — one statement per string (asyncpg does not support multi-
# statement strings or inline -- comments in text() calls)
# ---------------------------------------------------------------------------

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id         SERIAL PRIMARY KEY,
        name       VARCHAR(255) NOT NULL,
        email      VARCHAR(255) UNIQUE NOT NULL,
        plan_type  VARCHAR(50)  NOT NULL DEFAULT 'free',
        created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_wallets (
        id               SERIAL PRIMARY KEY,
        user_id          INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        tokens_remaining INT NOT NULL DEFAULT 100,
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions (
        id          SERIAL PRIMARY KEY,
        user_id     INT          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        type        VARCHAR(50)  NOT NULL,
        amount      INT          NOT NULL,
        description VARCHAR(500),
        created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS courses (
        id          SERIAL PRIMARY KEY,
        title       VARCHAR(255) NOT NULL,
        description TEXT,
        price       INT          NOT NULL DEFAULT 0,
        created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_enrollments (
        id          SERIAL PRIMARY KEY,
        user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        course_id   INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
        enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(user_id, course_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_documents (
        id          SERIAL PRIMARY KEY,
        user_id     INT          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        filename    VARCHAR(255) NOT NULL,
        vector_ids  TEXT[],
        uploaded_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    )
    """,
]

SEED_STATEMENTS = [
    """
    INSERT INTO users (id, name, email, plan_type) VALUES
        (1, 'Alice Smith', 'alice@example.com', 'premium'),
        (2, 'Bob Jones',   'bob@example.com',   'basic'),
        (3, 'Carol White', 'carol@example.com', 'free')
    ON CONFLICT DO NOTHING
    """,
    """
    INSERT INTO user_wallets (user_id, tokens_remaining) VALUES
        (1, 250), (2, 50), (3, 0)
    ON CONFLICT DO NOTHING
    """,
    """
    INSERT INTO courses (id, title, description, price) VALUES
        (1, 'Introduction to Python',      'Learn Python from scratch.',   50),
        (2, 'Advanced Machine Learning',   'Deep dive into ML algorithms.', 150),
        (3, 'Physics: Thermodynamics 101', 'Core concepts in thermodynamics.', 80)
    ON CONFLICT DO NOTHING
    """,
    """
    INSERT INTO user_enrollments (user_id, course_id) VALUES
        (1, 1), (1, 3), (2, 2)
    ON CONFLICT DO NOTHING
    """,
    """
    INSERT INTO transactions (user_id, type, amount, description) VALUES
        (1, 'credit_purchase',   500,  'Purchased 500 token pack'),
        (1, 'course_enrollment', -50,  'Enrolled in Introduction to Python'),
        (1, 'course_enrollment', -80,  'Enrolled in Physics: Thermodynamics 101'),
        (2, 'credit_purchase',   200,  'Purchased 200 token pack'),
        (2, 'course_enrollment', -150, 'Enrolled in Advanced Machine Learning')
    ON CONFLICT DO NOTHING
    """,
]


async def init_db() -> None:
    """
    Create tables and seed sample data.

    Each statement is executed individually because asyncpg does not support
    multi-statement strings or inline -- comments inside text() calls.
    """
    async with engine.begin() as conn:
        # Grant the current user rights to create objects in the public schema.
        # Required on PostgreSQL 15+ where the default public schema privilege
        # was revoked from non-superuser roles.
        await conn.execute(text("GRANT USAGE  ON SCHEMA public TO CURRENT_USER"))
        await conn.execute(text("GRANT CREATE ON SCHEMA public TO CURRENT_USER"))

        for stmt in DDL_STATEMENTS:
            await conn.execute(text(stmt))
        for stmt in SEED_STATEMENTS:
            await conn.execute(text(stmt))
    logger.info("Database schema initialized and seeded.")