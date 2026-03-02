
import logging
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import exc
from app.config import settings
from app.database.database import get_db_session
from app.schemas.models import ChatResponse, IntentSchema
from app.agent.token_guard import deduct_tokens, refund_tokens
from app.agent.utils import _get_llm
from app.agent.router.routing import _routing 
from app.agent.tool.sql_tool import _build_sql_tool
from app.agent.tool.rag_tool import _build_rag_tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Synthesis prompt
# ---------------------------------------------------------------------------

_SYNTHESIS_PROMPT = ChatPromptTemplate.from_messages(
    [
        SystemMessage(
            content=(
            """You are a helpful AI educational assistant. Answer the user's question clearly and concisely using ONLY the provided data.
            You must interpret the data appropriately:
            - Infer meaning from field names and values.
            - Treat it as excerpts from user-uploaded files.
            - Summarise or extract the relevant information to answer the question.
            If both structured data and document text are present, combine them into a single coherent answer.
            For SQL transaction data, synthesise the user's current balance and recent transactions with all information to answer questions about their account status. 
            For all transaction data, gather the same transaction and compute the summerise. Make sure all information is listed. 
            DO NOT expose raw SQL, vector IDs, internal tool names, or query identifiers.
            DO NOT repeat raw field names or JSON.
            Always synthesise the information into natural language."""
            )
        ),
        (
            "human",
            "User question: {question}\n\nRetrieved data:\n{context}\n\nPlease answer the question.",
        ),
    ]
)


# ---------------------------------------------------------------------------
# Main Coordinator Agent
# ---------------------------------------------------------------------------

class CoordinatorAgent:
    """
    LangChain-powered Coordinator Agent.

    Token strategy: deduct upfront, refund on any failure.
    This prevents users from getting free responses if the LLM errors,
    and eliminates the race condition window that exists with check-then-deduct.
    """
    
    async def _manage_tool(self, intent, user_id, db, message) -> str:
        #Defined tools here to pass the db and user_id context.
        tool_results: dict[str, str] = {}
        tool_used_labels: list[str] = []
        errors: list[str] = []
        sql_tool = _build_sql_tool(db, user_id)
        rag_tool = _build_rag_tool(db, user_id)

        tool_used_labels = []
        if intent.needs_sql:
            tool_used_labels.append("sql")
            queries_to_run = intent.sql_queries or ["user_profile"]
            for query_name in queries_to_run:
                print(f"Invoking SQL tool with query: {query_name}")  # Debug log to verify which queries are being run
                result_str: str = await sql_tool.arun({"query_name": query_name})
                if result_str.startswith("Error"):
                    errors.append(result_str)
                tool_results[f"sql:{query_name}"] = result_str

        
        # Invoke RAG tool.
        if intent.needs_rag:
            tool_used_labels.append("rag")
            rag_input = {
                "query": intent.rag_question or message,
                "filename": intent.rag_filename,
            }
            context_str: str = await rag_tool.arun(rag_input)
            if context_str.startswith("Document retrieval failed"):
                errors.append(context_str)
            tool_results["rag:context"] = context_str
        return tool_results, tool_used_labels, errors
    

    async def run(self, user_id: int, message: str) -> ChatResponse:
        """
        Process a user message end-to-end.

        Args:
            user_id: The requesting user.
            message: The user's natural language query.

        Returns:
            ChatResponse with the generated answer and updated token info.
        """
        async with get_db_session() as db:
            # Pre authorization and the pending the token deduction.
            try:
                balance_after_deduction = await deduct_tokens(
                db, user_id, description=f"Agent request: {message[:80]}")
                
            except ValueError:
                return ChatResponse(
                    user_id=user_id,
                    message=message,
                    response=(
                        "You've run out of tokens! You currently have 0 tokens remaining. "
                        "Please top up your account to continue using the assistant."
                    ),
                    tokens_used=0,
                    tokens_remaining=0,
                )

            # Routing the user query to the right tools and parsing the intent.
            try:
                intent: IntentSchema = await _routing(message)
            except Exception as exc:
                logger.error("Intent classification failed entirely: %s", exc)
                await refund_tokens(db, user_id, description="Refund: intent classification error")
                return ChatResponse(
                    user_id=user_id,
                    message=message,
                    response="I couldn't understand your request. Please try again.",
                    tokens_used=0,
                    tokens_remaining=balance_after_deduction + settings.token_cost,
                    error=str(exc),
                )

            # Managing the tools based on the parsed intent and collecting results.
            tool_results, tool_used_labels, errors = await self._manage_tool(intent, user_id, db, message)
            
            # Update the context block for synthesis with tool results. If a tool failed, its error message is included instead of data.
            context_block = "\n\n".join(
                f"[{key}]\n{value}" for key, value in tool_results.items()
            ) or "No tool data available."
            print(f"Context block for synthesis:\n{context_block}")  # Debug log to verify context passed to synthesis
            #Synthesise the final answer using the LLM, based on the retrieved context and original question.
            synthesis_chain = _SYNTHESIS_PROMPT | _get_llm(temperature=0.3)

            try:
                ai_message = await synthesis_chain.ainvoke(
                    {"question": message, "context": context_block}
                )
                answer: str = ai_message.content

            except Exception as exc:
                logger.error("LLM synthesis failed: %s", exc)
                await refund_tokens(db, user_id, description="Refund: synthesis LLM error")
                return ChatResponse(
                    user_id=user_id,
                    message=message,
                    response="I'm having trouble generating a response right now. Please try again.",
                    tokens_used=0,
                    tokens_remaining=balance_after_deduction + settings.token_cost,
                    error=str(exc),
                )

            #Return the successful response.
            tool_label = "/".join(tool_used_labels) if tool_used_labels else "llm_only"

            return ChatResponse(
                user_id=user_id,
                message=message,
                response=answer,
                tokens_used=settings.token_cost,
                tokens_remaining=balance_after_deduction,
                tool_used=tool_label,
                error="; ".join(errors) if errors else None,
            )
