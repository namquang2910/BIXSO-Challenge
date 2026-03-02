import re
import json
import logging
logger = logging.getLogger(__name__)
from app.config import settings
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

def _get_llm(temperature: float = 0.0):
    """
    Return the appropriate LangChain chat model based on settings.llm_provider.
    temperature=0.0 for deterministic routing; higher for natural synthesis.

    Supported providers (set LLM_PROVIDER in .env):
        anthropic -> Claude 3.5 Sonnet  (default)
        openai    -> GPT-4o-mini
        google    -> Gemini 2.0 Flash
    """
    if settings.llm_provider == "anthropic":
        return ChatAnthropic(
            model=settings.llm_model,
            anthropic_api_key=settings.anthropic_api_key,
            temperature=temperature,
            max_tokens=1024,
        )

    elif settings.llm_provider == "google":
        return ChatGoogleGenerativeAI(
            model=settings.llm_model,
            google_api_key=settings.google_api_key,
            temperature=temperature,
            max_output_tokens=1024,
        )

    elif settings.llm_provider == "ollama":
        return ChatOllama(
            model=settings.llm_model,       # e.g. "llama3.2", "mistral", "qwen2.5"
            base_url=settings.ollama_url,   # default: http://localhost:11434
            temperature=temperature,
            num_predict=1024,
        )

    else:  # openai
        return ChatOpenAI(
            model="gpt-4o-mini",
            openai_api_key=settings.openai_api_key,
            temperature=temperature,
        )


def _format_output(raw):
        # Strip markdown fences if model adds them
        raw = re.sub(r"^```[a-z]*\n", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        # Extract first JSON object if model adds extra text
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON found in response: {raw[:200]}")
        data = json.loads(match.group(0))
        print("Raw model output:", raw)  # Debug log to verify model output
        print("Extracted JSON data:", data)  # Debug log to verify extracted JSON
        # Validate sql_queries — reject any invented names
        valid_queries = {"token_balance", "last_transaction", "all_transactions",
                         "enrolled_courses", "available_courses", "user_profile"}
        safe_queries = [q for q in (data.get("sql_queries") or []) if q in valid_queries]
        print("Validated sql_queries:", safe_queries)  # Debug log to verify validated queries
        if len(safe_queries) != len(data.get("sql_queries") or []):
            logger.warning("Ollama returned invalid sql_queries — filtered to: %s", safe_queries)
        return data, safe_queries