"""
Application configuration loaded from environment variables.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM — supports "anthropic" (Claude 3.5 Sonnet) or "openai" (GPT-4o-mini)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = "AIzaSyAjD8pFv6rx4dy6itQi0Mc4pY4g2R-zBHA"
    llm_provider: str = "ollama"
    llm_model: str = "llama3.2"
    ollama_url: str = "http://localhost:11434"
    # Database (PostgreSQL async)
    database_url: str = "postgresql+asyncpg://namquang2017@localhost:5432/bixso_edu"

    # Qdrant vector store
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "user_documents"

    # Embeddings — OpenAI text-embedding-3-small via LangChain
    embedding_model: str = "text-embedding-3-small"

    # RAG chunking strategy
    chunk_size: int = 512    # characters per chunk
    chunk_overlap: int = 64  # character overlap between chunks
    rag_top_k: int = 5       # number of chunks to retrieve

    # Token cost per successful agent interaction
    token_cost: int = 10

    class Config:
        env_file = ".env"


settings = Settings()
