import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from app.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.vector_db import _get_qdrant_client, _ensure_collection, _get_vector_store
from sqlalchemy import text

logger = logging.getLogger(__name__)

def _extract_pdf_text(raw_bytes: bytes) -> str:
    """
    Extract plain text from a PDF using pypdf (if installed).
    Falls back to raw byte decoding if pypdf is not available.
    """
    try:
        import io
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    except ImportError:
        logger.warning("pypdf not installed — treating PDF as plain text. Run: pip install pypdf")
        return raw_bytes.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.error("PDF extraction failed: %s", exc)
        return raw_bytes.decode("utf-8", errors="replace")
    
def _get_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

async def ingest_document(
    db: AsyncSession,
    user_id: int,
    filename: str,
    content: str,
    is_file: bool = False
) -> int:
    splitter = _get_splitter()
    
    raw_chunks = splitter.split_text(content)
    logger.info("Ingesting '%s' for user %d — %d chunks.", filename, user_id, len(raw_chunks))

    documents = [
        Document(
            page_content=chunk,
            metadata={
                "user_id": user_id,
                "filename": filename,
                "chunk_index": i,
            },
        )
        for i, chunk in enumerate(raw_chunks)
    ]

    client = _get_qdrant_client()
    _ensure_collection(client)

    vector_store = _get_vector_store()
    chunk_ids: list[str] = vector_store.add_documents(documents)
    logger.info("Upserted %d vectors into Qdrant for user %d.", len(chunk_ids), user_id)

    result = await db.execute(
        text(
            """
            INSERT INTO user_documents (user_id, filename, vector_ids)
            VALUES (:user_id, :filename, :vector_ids)
            ON CONFLICT DO NOTHING
            RETURNING id
            """
        ),
        {"user_id": user_id, "filename": filename, "vector_ids": chunk_ids},
    )
    row = result.fetchone()
    doc_id: int = row[0] if row else -1
    logger.info("Stored document metadata with id=%d.", doc_id)
    return doc_id