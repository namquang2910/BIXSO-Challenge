"""
RAG Tool: Document ingestion and semantic retrieval via LangChain + Qdrant.
"""

import logging
from typing import Optional

from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, Filter, FieldCondition, MatchValue
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.vector_db import _get_qdrant_client, _ensure_collection, _get_vector_store
from app.rag.embedding import _get_embeddings
from app.rag.ingest_doc import ingest_document
from app.config import settings
logger = logging.getLogger(__name__)


async def retrieve_context(
    db: AsyncSession,
    user_id: int,
    query: str,
    filename: Optional[str] = None,
    top_k: Optional[int] = None) -> str:
    
    top_k = top_k or settings.rag_top_k

    #Ensure the user have at least one document in the database (SQL and Qdrant)
    check = await db.execute(
        text("SELECT id FROM user_documents WHERE user_id = :user_id LIMIT 1"),
        {"user_id": user_id})
    
    if not check.fetchone():
        logger.info("DEBUG No documents in Postgres for user_id=%d", user_id)
        return "No documents found for this user."

    # Filter the search by user_id and the filename if it provided.
    conditions = must_conditions = [FieldCondition(key="metadata.user_id", match=MatchValue(value=user_id))] # Always filter by user_id 
     #The filename will be extracted by the agent from the user query
    conditions.append(FieldCondition(key="metadata.filename", match=MatchValue(value=filename))) if filename else None # Optional filter by filename if provided
    #Filter the search
    qdrant_filter = Filter(must=conditions)
    logger.info("DEBUG Qdrant filter: user_id=%d filename=%s", user_id, filename)


    #Access the vector store and perform similarity search with the constructed filter
    vector_store = _get_vector_store()
    results = vector_store.similarity_search_with_score(
        query=query,
        k=top_k,
        filter=qdrant_filter,
    )
    logger.info("DEBUG similarity_search returned %d results", len(results))
    chunks = [doc.page_content for doc, _score in results]

    #If the result is empty.
    if not results:
        #Tried to search without the filename filter
        qdrant_filter = Filter(must=must_conditions)
        unfiltered = vector_store.similarity_search_with_score(query=query, k=top_k, filter=qdrant_filter)
        logger.info("DEBUG unfiltered search returned %d results", len(unfiltered))
        chunks = [doc.page_content for doc, _score in unfiltered]
        return "No relevant content found in the specified document."

    return "\n\n---\n\n".join(chunks)
