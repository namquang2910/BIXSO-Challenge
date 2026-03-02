"""
Token Guard: Enforces token balance checks and deductions.

Every agent interaction must:
1. Check tokens_remaining > 0.
2. On successful response, deduct TOKEN_COST (10) tokens.
3. Log the deduction as a transaction.
"""

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


async def get_token_balance(db: AsyncSession, user_id: int) -> int:
    """Return the current token balance for a user."""
    result = await db.execute(
        text("SELECT tokens_remaining FROM user_wallets WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    row = result.fetchone()
    if row is None:
        raise ValueError(f"No wallet found for user_id={user_id}")
    return int(row[0])


async def check_tokens(db: AsyncSession, user_id: int) -> tuple[bool, int]:
    """
    Check whether the user has enough tokens.

    Returns:
        (has_tokens: bool, current_balance: int)
    """
    balance = await get_token_balance(db, user_id)
    return balance > 0, balance


async def deduct_tokens(
    db: AsyncSession,
    user_id: int,
    description: str = "Agent interaction",
) -> int:
    """
    Deduct TOKEN_COST tokens from the user's wallet and log the transaction.

    Args:
        db:          Active DB session.
        user_id:     The user to deduct from.
        description: Human-readable reason for the deduction.

    Returns:
        New token balance after deduction.

    Raises:
        ValueError: If the user has insufficient tokens.
    """
    # Re-check balance inside the transaction to prevent race conditions
    balance = await get_token_balance(db, user_id)
    if balance < settings.token_cost:
        raise ValueError(
            f"Insufficient tokens. Balance: {balance}, Required: {settings.token_cost}"
        )

    # Atomic deduction
    await db.execute(
        text(
            """
            UPDATE user_wallets
            SET tokens_remaining = tokens_remaining - :cost,
                updated_at       = NOW()
            WHERE user_id = :user_id
            """
        ),
        {"cost": settings.token_cost, "user_id": user_id},
    )

    # Record the transaction
    await db.execute(
        text(
            """
            INSERT INTO transactions (user_id, type, amount, description)
            VALUES (:user_id, 'agent_usage', :amount, :description)
            """
        ),
        {
            "user_id":     user_id,
            "amount":      -settings.token_cost,
            "description": description,
        },
    )

    new_balance = balance - settings.token_cost
    logger.info("Deducted %d tokens from user %d. New balance: %d", settings.token_cost, user_id, new_balance)
    return new_balance


async def refund_tokens(
    db: AsyncSession,
    user_id: int,
    description: str = "Agent error refund",
) -> int:
    """
    Refund TOKEN_COST tokens back to the user's wallet.

    Called when tokens were pre-deducted but the agent failed to produce
    a successful response. Logs the refund as a credit transaction.

    Args:
        db:          Active DB session.
        user_id:     The user to refund.
        description: Human-readable reason for the refund.

    Returns:
        New token balance after refund.
    """
    await db.execute(
        text(
            """
            UPDATE user_wallets
            SET tokens_remaining = tokens_remaining + :cost,
                updated_at       = NOW()
            WHERE user_id = :user_id
            """
        ),
        {"cost": settings.token_cost, "user_id": user_id},
    )

    await db.execute(
        text(
            """
            INSERT INTO transactions (user_id, type, amount, description)
            VALUES (:user_id, 'agent_refund', :amount, :description)
            """
        ),
        {
            "user_id":     user_id,
            "amount":      settings.token_cost,
            "description": description,
        },
    )

    balance = await get_token_balance(db, user_id)
    logger.info("Refunded %d tokens to user %d. New balance: %d", settings.token_cost, user_id, balance)
    return balance