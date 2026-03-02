import re
from typing import Any
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field as PydanticField
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config import settings
logger = logging.getLogger(__name__)


# Keywords that indicate a destructive or data-modifying statement
_DESTRUCTIVE_PATTERN = re.compile(
    r"\b(DELETE|DROP|UPDATE|INSERT|ALTER|TRUNCATE|GRANT|REVOKE|CREATE|REPLACE)\b",
    re.IGNORECASE,
)


def _is_safe_query(sql: str) -> bool:
    """Return True only if the query is a plain SELECT."""
    stripped = sql.strip().upper()
    if _DESTRUCTIVE_PATTERN.search(stripped):
        return False
    if not stripped.startswith("SELECT"):
        return False
    return True


async def execute_sql_query(
    db: AsyncSession,
    sql: str,
    user_id: int,
) -> list[dict[str, Any]]:
    """
    Execute a parameterized read-only SQL query.

    Args:
        db:      Active async DB session.
        sql:     The SQL string to execute. Must be a SELECT statement.
                 Use :user_id as a placeholder where user scoping is needed.
        user_id: The requesting user's ID (injected into query params).

    Returns:
        List of row dicts.

    Raises:
        ValueError: If the query contains destructive keywords.
    """
    if not _is_safe_query(sql):
        raise ValueError(
            "Security violation: Only SELECT statements are permitted. "
            "Destructive operations (DELETE, DROP, UPDATE, etc.) are blocked."
        )

    try:
        result = await db.execute(text(sql), {"user_id": user_id})
        rows = result.mappings().all()
        return [dict(row) for row in rows]
    except Exception as exc:
        logger.error("SQL execution error: %s | Query: %s", exc, sql)
        raise RuntimeError(f"Database query failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Pre-built named queries the agent can select from
# ---------------------------------------------------------------------------

NAMED_QUERIES: dict[str, str] = {
    "token_balance": """
        SELECT tokens_remaining
        FROM user_wallets
        WHERE user_id = :user_id
    """,

    "last_transaction": """
        SELECT type, amount, description, created_at
        FROM transactions
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT 1
    """,

    "all_transactions": """
        SELECT type, amount, description, created_at
        FROM transactions
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT 30
    """,

    "enrolled_courses": """
        SELECT c.id, c.title, c.description, c.price, ue.enrolled_at
        FROM courses c
        JOIN user_enrollments ue ON ue.course_id = c.id
        WHERE ue.user_id = :user_id
        ORDER BY ue.enrolled_at DESC
    """,

    "available_courses": """
        SELECT id, title, description, price
        FROM courses
        ORDER BY title
    """,

    "user_profile": """
        SELECT u.id, u.name, u.email, u.plan_type, w.tokens_remaining
        FROM users u
        JOIN user_wallets w ON w.user_id = u.id
        WHERE u.id = :user_id
    """,
}


async def run_named_query(
    db: AsyncSession,
    query_name: str,
    user_id: int,
) -> list[dict[str, Any]]:
    """
    Execute a named (pre-approved, read-only) query.

    Args:
        db:         Active async DB session.
        query_name: Key from NAMED_QUERIES.
        user_id:    Requesting user's ID.

    Returns:
        List of row dicts.

    Raises:
        KeyError: If query_name is not in NAMED_QUERIES.
    """
    if query_name not in NAMED_QUERIES:
        raise KeyError(f"Unknown named query: '{query_name}'. Available: {list(NAMED_QUERIES)}")

    sql = NAMED_QUERIES[query_name]
    return await execute_sql_query(db, sql, user_id)


def _build_sql_tool(db, user_id: int) -> StructuredTool:
    """
    Create a LangChain StructuredTool that executes named SQL queries.
    The tool is pre-bound to the current DB session and user_id so the
    LLM cannot supply a different user_id.
    """

    class SqlInput(BaseModel):
        query_name: str = PydanticField(
            description=(
                "Named query to execute. One of: token_balance, last_transaction, "
                "all_transactions, enrolled_courses, available_courses, user_profile."
            )
        )

    async def run_sql(query_name: str) -> str:
        try:
            rows = await run_named_query(db, query_name, user_id)
            return json.dumps(rows, default=str)
        except (KeyError, RuntimeError, ValueError) as exc:
            logger.error("SQL tool error for '%s': %s", query_name, exc)
            return f"Error executing query '{query_name}': {exc}"

    return StructuredTool.from_function(
        coroutine=run_sql,
        name="sql_query",
        description=(
            "Execute a read-only named SQL query to retrieve user data such as "
            "token balance, transactions, or course enrolments."
        ),
        args_schema=SqlInput,
    )
