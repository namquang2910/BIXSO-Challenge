"""
Pydantic models for API request and response validation.
"""
from pydantic import BaseModel, Field as PydanticField
from pydantic import BaseModel, Field
from typing import Optional


class ChatRequest(BaseModel):
    user_id: int = Field(..., description="The ID of the requesting user.", example=1)
    message: str = Field(..., description="The user's natural language message.", example="How many tokens do I have?")


class ChatResponse(BaseModel):
    user_id: int
    message: str
    response: str
    tokens_used: int = Field(default=0, description="Tokens deducted this interaction (0 if refused).")
    tokens_remaining: Optional[int] = Field(default=None, description="Remaining token balance after this interaction.")
    tool_used: Optional[str] = Field(default=None, description="Which tool was invoked: 'sql', 'rag', 'both', or None.")
    error: Optional[str] = Field(default=None, description="Error message if something went wrong.")

class IntentSchema(BaseModel):
    """Structured output schema for intent classification."""

    needs_sql: bool = PydanticField(
        description="True if the query requires database lookups (balance, courses, transactions)."
    )
    needs_rag: bool = PydanticField(
        description="True if the query asks about content from an uploaded document."
    )
    sql_queries: list[str] = PydanticField(
        default_factory=list,
        description=(
            "Named queries to run. Valid values: token_balance, last_transaction, "
            "all_transactions, enrolled_courses, available_courses, user_profile."
        ),
    )
    rag_filename: Optional[str] = PydanticField(
        default=None,
        description="Filename mentioned in the query (e.g. 'Physics_Notes.pdf'), or null.",
    )
    rag_question: Optional[str] = PydanticField(
        default=None,
        description="The core question to search for inside the document.",
    )
