from langchain_huggingface import HuggingFaceEmbeddings
from app.config import settings

def _get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=settings.embedding_model)
