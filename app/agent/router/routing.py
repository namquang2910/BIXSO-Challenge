

from asyncio.log import logger
import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage
from app.config import settings
from app.agent.utils import _get_llm
from app.schemas.models import IntentSchema
from app.agent.prompts import ROUTER_PROMPT
from app.agent.utils import _format_output

async def _routing(message: str) -> IntentSchema:
    """
    Classify the user's intent.

    Priority order:
    1. If message contains a .pdf filename, then use RAG
    2. Ollama provider → use plain JSON prompt (the small model can not work with structured output).
    3. Other providers → use LangChain with_structured_output.
    4. Any failure → keyword fallback.
    """
    # PDF filename present → force RAG immediately, no LLM needed
    pdf_match = re.search(r"[\w\-]+\.pdf", message, re.IGNORECASE)
    if pdf_match:
        logger.info("PDF filename detected — routing directly to RAG.")
        return IntentSchema(
            needs_sql=False,
            needs_rag=True,
            sql_queries=[],
            rag_filename=pdf_match.group(0),
            rag_question=message,
        )
    
    # Rule 2: Ollama — use plain JSON prompting
    if settings.llm_provider == "ollama":
        return await _local_model(message)

    # Rule 3: Cloud providers — use structured output
    if settings.llm_provider in {"anthropic", "google_genai", "openai"}:
        return await _cloud_model(message)
    
async def _local_model(message: str) -> IntentSchema:
    """
    Ollama-specific intent classification using plain JSON prompting.
    Avoids with_structured_output which is unreliable with local models.
    """
    # Hard-code the allowed SQL query names in the prompt so the model
    # cannot invent new ones
    json_system = (
        ROUTER_PROMPT + """
        Respond ONLY with a JSON object. No markdown. No explanation. Example:
        {"needs_sql": false, "needs_rag": true, "sql_queries": [], "rag_filename": "Notes.pdf", "rag_question": "explain the task"}
        """
    )
    print("JSON system prompt:", json_system)  # Debug log to verify prompt content
    json_prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=json_system),
        ("human", "{message}"),
    ])

    try:
        llm = _get_llm(temperature=0.0)
        chain = json_prompt | llm
        ai_msg = await chain.ainvoke({"message": message})
        raw = ai_msg.content.strip()
        data, safe_queries = _format_output(raw)

        return IntentSchema(
            needs_sql=bool(data.get("needs_sql", False)),
            needs_rag=bool(data.get("needs_rag", False)),
            sql_queries=safe_queries,
            rag_filename=data.get("rag_filename"),
            rag_question=data.get("rag_question"),
        )
    except Exception as exc:
        logger.warning("Ollama intent classification failed (%s) -- using keyword fallback.", exc)
        return IntentSchema(
            needs_sql=False,
            needs_rag=False,
            sql_queries=[],
            rag_filename=None,
            rag_question=None,
        )

async def _cloud_model(message: str) -> IntentSchema:
    """
    Cloud model intent classification using LangChain's with_structured_output.
    """
    try:
        _classify_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=ROUTER_PROMPT),
                ("human", "{message}"),
            ])
        llm = _get_llm(temperature=0.0)
        structured_llm = llm.with_structured_output(IntentSchema)
        chain = _classify_prompt | structured_llm
        result: IntentSchema = await chain.ainvoke({"message": message})
        return result
    except Exception as e:
        logger.warning("Cloud model intent classification failed (%s) -- using keyword fallback.", e)
        return IntentSchema(
            needs_sql=False,
            needs_rag=False,
            sql_queries=[],
            rag_filename=None,
            rag_question=None,
        )