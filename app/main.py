"""
BIXSO Agentic Educator - Main FastAPI Application
Coordinator Agent with SQL, RAG, and Token Management
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.schemas.models import ChatRequest, ChatResponse
from app.rag.ingest_doc import _extract_pdf_text, ingest_document
from app.agent.agent import CoordinatorAgent
from app.database.database import init_db, get_db_session
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    logger.info("Startup complete.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="BIXSO Agentic Educator",
    description="AI Coordinator Agent for educational content, SQL queries, and RAG retrieval.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "BIXSO Agentic Educator"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint. Routes user query through the Coordinator Agent.
    """
    agent = CoordinatorAgent()
    return await agent.run(user_id=request.user_id, message=request.message)


@app.post("/documents/upload-file")
async def upload_document(
    user_id: int = Form(...),
    file: UploadFile = File(...),
):
    raw_bytes = await file.read()
    filename = file.filename or "uploaded_file"

    # Extract text depending on file type
    if filename.lower().endswith(".pdf"):
        content = _extract_pdf_text(raw_bytes)
    else:
        # Treat as plain text (works for .txt, .md, .csv, etc.)
        content = raw_bytes.decode("utf-8", errors="replace")

    if not content.strip():
        return {"error": "Could not extract any text from the file."}, 400

    async with get_db_session() as db:
        doc_id = await ingest_document(db=db, user_id=user_id, filename=filename, content=content)

    return {
        "message": "Document ingested successfully",
        "document_id": doc_id,
        "filename": filename,
        "characters_ingested": len(content),
    }

