from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field as PydanticField
import json
import logging
from typing import Optional
from app.rag.rag import retrieve_context

logger = logging.getLogger(__name__)

def _build_rag_tool(db, user_id: int) -> StructuredTool:
    """
    Create a LangChain StructuredTool that retrieves document context from Qdrant.
    The user_id is pre-bound -- the LLM cannot override it.
    """

    class RagInput(BaseModel):
        query: str = PydanticField(
            description="The question to search for in the user's documents."
        )
        filename: Optional[str] = PydanticField(
            default=None,
            description="Restrict search to this filename, e.g. 'Physics_Notes.pdf'.",
        )

    async def run_rag(query: str, filename: Optional[str] = None) -> str:
        try:
            print(f"RAG tool invoked with query='{query}' and filename='{filename}' for user_id={user_id}")
            return await retrieve_context(
                db=db,
                user_id=user_id,
                query=query,
                filename=filename,
            )
        except Exception as exc:
            logger.error("RAG tool error: %s", exc)
            return f"Document retrieval failed: {exc}"

    return StructuredTool.from_function(
        coroutine=run_rag,
        name="rag_retrieval",
        description=(
            "Retrieve relevant passages from the user's uploaded documents using "
            "semantic (vector) search against Qdrant."
        ),
        args_schema=RagInput,
    )
