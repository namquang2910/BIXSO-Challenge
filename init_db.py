"""
scripts/seed.py — Seed or RESET sample data.

Usage:
    python -m scripts.seed          # seed only (skip existing rows)
    python -m scripts.seed --reset  # reset balances and transactions back to defaults
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database.database import init_db, get_db_session


RESET_SQL = [
    # Reset token balances to original values
    """
    INSERT INTO user_wallets (user_id, tokens_remaining)
    VALUES (1, 250), (2, 50), (3, 0)
    ON CONFLICT (user_id) DO UPDATE
        SET tokens_remaining = EXCLUDED.tokens_remaining,
            updated_at       = NOW()
    """,
    # Wipe all agent_usage and refund transactions, keep the original ones
    """
    DELETE FROM transactions
    WHERE type IN ('agent_usage', 'agent_refund')
    """,
]


async def seed():
    """Create schema and insert rows that don't exist yet."""
    print("Initializing database schema and seeding sample data...")
    await init_db()
    print("Done.")
    _print_users()


async def reset():
    """Reset balances and clean up transactions without touching schema or enrollments."""
    print("Resetting token balances and clearing agent transactions...")

    async with get_db_session() as db:
        for stmt in RESET_SQL:
            await db.execute(text(stmt))

        await db.commit()  # 🔥 REQUIRED

    print("Done! Balances restored:")
    _print_users()

async def show_wallets():
    async with get_db_session() as db:
        result = await db.execute(
            text("SELECT user_id, tokens_remaining FROM user_wallets ORDER BY user_id")
        )
        rows = result.fetchall()

    print("\nCurrent wallet balances:")
    for r in rows:
        print(f"user_id={r.user_id}  tokens={r.tokens_remaining}")

def _print_users():
    print("\n  user_id=1  Alice  · premium · 250 tokens · enrolled in Python + Physics")
    print("  user_id=2  Bob    · basic   · 50 tokens  · enrolled in ML")
    print("  user_id=3  Carol  · free    · 0 tokens   · no enrollments")


async def main():
    if "--reset" in sys.argv:
        await reset()
    else:
        await seed()
    print("Done! Balances restored:")
    await show_wallets()

if __name__ == "__main__":
    asyncio.run(main())
