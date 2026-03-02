
from qdrant_client import QdrantClient
from app.config import settings
import logging
from langchain_qdrant import QdrantVectorStore
from qdrant_client.models import Distance, VectorParams
from app.rag.embedding import _get_embeddings

logger = logging.getLogger(__name__)


def _get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def _ensure_collection(client: QdrantClient, vector_size: int = 384) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s'.", settings.qdrant_collection)


def _get_vector_store() -> QdrantVectorStore:
    return QdrantVectorStore(
        client=_get_qdrant_client(),
        collection_name=settings.qdrant_collection,
        embedding=_get_embeddings(),
    )
