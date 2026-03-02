# BIXSO Agentic Educator

An AI-powered educational assistant built with **FastAPI + LangChain + Qdrant + PostgreSQL**. It routes natural language queries to the right tool — SQL for account/course data, RAG for uploaded documents — while enforcing a token-based usage budget.

---

## How It Works

```
POST /chat
     │
     ▼
Token Guard
  ├── 0 tokens? → Refuse immediately ("Please top up")
  └── tokens OK → Deduct upfront (refund on failure)
     │
     ▼
Intent Router  (LLM-based classification)
  ├── PDF filename detected? → Force RAG (no LLM call needed)
  ├── Ollama provider       → Plain JSON prompt
  └── Cloud provider        → LangChain with_structured_output → IntentSchema
     │
     ├── needs_sql=true → SQL Tool (named read-only queries against PostgreSQL)
     ├── needs_rag=true → RAG Tool (semantic search in Qdrant, scoped to user)
     └── both=true      → SQL Tool + RAG Tool (sequential)
     │
     ▼
Synthesis LLM  (ChatPromptTemplate → natural language answer)
     │
     ▼
ChatResponse { response, tokens_used, tokens_remaining, tool_used }
```

---

## Module Breakdown

| Module | Responsibility |
|---|---|
| `app/main.py` | FastAPI routes (`/chat`, `/documents/upload-file`) and lifespan hooks |
| `app/agent/agent.py` | Coordinator Agent — orchestrates token guard, router, tools, and synthesis |
| `app/agent/router/routing.py` | Intent classification — PDF shortcut, Ollama JSON path, cloud structured output |
| `app/agent/prompts.py` | System prompts for the router |
| `app/agent/tool/sql_tool.py` | Named read-only SQL queries with destructive-keyword blocking |
| `app/agent/tool/rag_tool.py` | LangChain StructuredTool wrapper around Qdrant retrieval |
| `app/agent/token_guard.py` | Token balance check, atomic deduction, and refund on error |
| `app/agent/utils.py` | LLM factory (`_get_llm`) supporting Anthropic, OpenAI, Google, Ollama |
| `app/rag/rag.py` | Qdrant similarity search with user-scoped metadata filter |
| `app/rag/ingest_doc.py` | PDF/text extraction, LangChain chunking, Qdrant upsert |
| `app/rag/embedding.py` | HuggingFace `all-MiniLM-L6-v2` embeddings (local, no API key needed) |
| `app/database/database.py` | Schema DDL, async session factory, seed data |
| `app/database/vector_db.py` | Qdrant client, collection management, vector store factory |
| `app/schemas/models.py` | Pydantic request/response models (`ChatRequest`, `ChatResponse`, `IntentSchema`) |
| `app/config.py` | All settings loaded from `.env` via Pydantic |

---

## LangChain Components Used

| Component | Location | Purpose |
|---|---|---|
| `ChatAnthropic` / `ChatOpenAI` / `ChatGoogleGenerativeAI` / `ChatOllama` | `agent/utils.py` | Pluggable LLM backends |
| `with_structured_output(IntentSchema)` | `router/routing.py` | Coerces cloud LLM output into a typed Pydantic schema |
| `ChatPromptTemplate` | `agent.py`, `router/routing.py` | Reusable prompt templates for routing and synthesis |
| `StructuredTool.from_function` | `tool/sql_tool.py`, `tool/rag_tool.py` | Typed LangChain tools with pre-bound `user_id` |
| `RecursiveCharacterTextSplitter` | `rag/ingest_doc.py` | Paragraph/sentence-aware text chunking |
| `HuggingFaceEmbeddings` | `rag/embedding.py` | Local embeddings via `all-MiniLM-L6-v2` (384 dimensions) |
| `QdrantVectorStore` | `database/vector_db.py` | Stores and retrieves vectors with user-scoped metadata filtering |

---

## Available SQL Queries

The agent can only invoke these pre-approved named queries — it cannot write arbitrary SQL:

| Query Name | What It Returns |
|---|---|
| `token_balance` | Current token balance from `user_wallets` |
| `last_transaction` | Most recent row from `transactions` |
| `all_transactions` | Last 30 rows from `transactions` |
| `enrolled_courses` | Courses the user is enrolled in |
| `available_courses` | All courses available to purchase |
| `user_profile` | Name, email, plan type, and token balance |

---

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Qdrant (Docker recommended)
- At least one LLM provider configured (Ollama is the default)

### 1. Start Qdrant

```bash
docker run -p 6333:6333 qdrant/qdrant
```

### 2. Create the database

```bash
createdb bixso_edu
```

### 3. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.sample .env
# Edit .env — set your API keys and DATABASE_URL
```

Key settings in `.env`:

```ini
LLM_PROVIDER=ollama          # ollama | anthropic | openai | google
LLM_MODEL=llama3.2
OLLAMA_URL=http://localhost:11434

ANTHROPIC_API_KEY=""
OPENAI_API_KEY=""
GOOGLE_API_KEY=""

DATABASE_URL=postgresql+asyncpg://user@localhost:5432/bixso_edu

QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=user_documents

EMBEDDING_MODEL=text-embedding-3-small
CHUNK_SIZE=512
CHUNK_OVERLAP=64
RAG_TOP_K=5
TOKEN_COST=5
```

### 5. Seed the database

```bash
python -m scripts.init_db
```

To reset balances and clear agent transactions later:

```bash
python -m scripts.init_db --reset
```

### 6. Start the API

```bash
uvicorn app.main:app --reload --port 8000
```

- API: `http://localhost:8000`
- Interactive docs: `http://localhost:8000/docs`

### 7. (Optional) Launch the Streamlit UI

```bash
streamlit run app_ui.py
```

---

## API Reference

### `GET /health`

```bash
curl http://localhost:8000/health
```

```json
{ "status": "ok", "service": "BIXSO Agentic Educator" }
```

---

### `POST /chat`

**Request:**
```json
{
  "user_id": 1,
  "message": "How many tokens do I have left?"
}
```

**Response:**
```json
{
  "user_id": 1,
  "message": "How many tokens do I have left?",
  "response": "You currently have 245 tokens remaining.",
  "tokens_used": 5,
  "tokens_remaining": 245,
  "tool_used": "sql",
  "error": null
}
```

---

### `POST /documents/upload-file`

Upload a `.pdf` or `.txt` file for RAG ingestion (stored in Qdrant).

**Request (multipart/form-data):**
- `user_id` — integer
- `file` — the file to upload

**Response:**
```json
{
  "message": "Document ingested successfully",
  "document_id": 7,
  "filename": "Physics_Notes.pdf",
  "characters_ingested": 14320
}
```

---

## Example curl Commands

### Check token balance

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "message": "How many tokens do I have left?"}'
```

### Show last transaction

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "message": "What was my last transaction?"}'
```

### Show all transactions

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "message": "Show me all my transactions."}'
```

### Show enrolled courses

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "message": "Which courses am I currently enrolled in?"}'
```

### Show user profile

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "message": "Show my account profile."}'
```

### Combined SQL query (balance + courses)

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "message": "Do I have enough tokens to start a quiz, and which courses am I enrolled in?"}'
```

### Upload a document for RAG

```bash
curl -X POST http://localhost:8000/documents/upload-file \
  -F "user_id=1" \
  -F "file=@/path/to/Physics_Notes.pdf"
```

### Query an uploaded document

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "message": "Based on my Physics_Notes.pdf, explain the second law of thermodynamics."}'
```

### Zero-token user (user_id=3)

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": 3, "message": "Show my courses."}'
```

Expected: polite refusal with `tokens_used: 0`.

---

## Sample Users (Seeded)

| user_id | Name | Plan | Tokens | Enrollments |
|---|---|---|---|---|
| 1 | Alice Smith | premium | 250 | Python, Thermodynamics |
| 2 | Bob Jones | basic | 50 | Machine Learning |
| 3 | Carol White | free | 0 | None |

---

## RAG Strategy

### Chunking — `RecursiveCharacterTextSplitter`
- **Chunk size:** 512 characters
- **Overlap:** 64 characters
- **Separators:** `["\n\n", "\n", ". ", " ", ""]` — splits on paragraphs first, then sentences, then words

### Embedding — `HuggingFaceEmbeddings`
- **Model:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions, runs fully locally)
- No API key required for embeddings

### Vector Store — `QdrantVectorStore`
- **Backend:** Qdrant (self-hosted via Docker)
- **Ingestion:** `vector_store.add_documents(documents)` — LangChain handles embedding and upsert
- **Retrieval:** `similarity_search_with_score` with a mandatory `user_id` metadata filter

---

## Security

- **SQL injection:** All queries use SQLAlchemy `text()` with bound parameters — no string interpolation.
- **Destructive SQL blocked:** Regex guard rejects `DELETE`, `DROP`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE`. Only `SELECT` passes.
- **User-scoped RAG:** Every Qdrant query enforces a `user_id` metadata filter — users cannot access each other's documents.
- **Pre-bound tools:** `StructuredTool` instances are built per-request with `user_id` pre-bound — the LLM cannot supply a different user.
- **Token race condition:** Balance is re-checked inside the same DB transaction as the deduction; tokens are deducted upfront and refunded on failure.

---

## Running Tests

```bash
pytest tests/ -v
```