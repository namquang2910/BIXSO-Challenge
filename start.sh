#!/usr/bin/env bash
# =============================================================================
# BIXSO Agentic Educator — start.sh
# Boots all Docker services, pulls the Ollama model, and seeds the database.
# Usage:
#   ./start.sh            # normal start
#   ./start.sh --reset    # reset DB balances + clear agent transactions
#   ./start.sh --down     # stop and remove all containers
#   ./start.sh --rebuild  # force rebuild images then start
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║      BIXSO Agentic Educator          ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"

# ── Argument parsing ──────────────────────────────────────────────────────────
MODE="start"
for arg in "$@"; do
  case "$arg" in
    --down)    MODE="down" ;;
    --reset)   MODE="reset" ;;
    --rebuild) MODE="rebuild" ;;
    --help|-h)
      echo "Usage: ./start.sh [--down | --reset | --rebuild]"
      echo ""
      echo "  (no flag)  Build images (if needed) and start all services"
      echo "  --rebuild  Force-rebuild all images then start"
      echo "  --reset    Start services, then reset DB balances"
      echo "  --down     Stop and remove all containers"
      exit 0
      ;;
  esac
done

# ── Preflight checks ──────────────────────────────────────────────────────────
check_dependency() {
  if ! command -v "$1" &>/dev/null; then
    error "'$1' is not installed or not in PATH."
    exit 1
  fi
}

check_dependency docker
check_dependency docker compose 2>/dev/null || check_dependency "docker-compose"

# Prefer 'docker compose' (V2) over 'docker-compose' (V1)
if docker compose version &>/dev/null 2>&1; then
  DC="docker compose"
else
  DC="docker-compose"
fi

# ── .env guard ────────────────────────────────────────────────────────────────
if [[ ! -f ".env" ]]; then
  if [[ -f ".env.sample" ]]; then
    warn ".env not found — copying from .env.sample"
    cp .env.sample .env
    warn "Please edit .env with your API keys before continuing."
    exit 1
  else
    warn ".env not found — continuing with docker-compose defaults."
  fi
fi

# ── Load .env for OLLAMA model name ──────────────────────────────────────────
OLLAMA_MODEL="${LLM_MODEL:-llama3.2}"
if [[ -f ".env" ]]; then
  OLLAMA_MODEL_FROM_ENV=$(grep -E '^LLM_MODEL=' .env | cut -d'=' -f2 | tr -d '"' | tr -d "'")
  if [[ -n "$OLLAMA_MODEL_FROM_ENV" ]]; then
    OLLAMA_MODEL="$OLLAMA_MODEL_FROM_ENV"
  fi
fi

# ── --down ────────────────────────────────────────────────────────────────────
if [[ "$MODE" == "down" ]]; then
  info "Stopping all containers..."
  $DC down
  success "All containers stopped."
  exit 0
fi

# ── Build / start ─────────────────────────────────────────────────────────────
if [[ "$MODE" == "rebuild" ]]; then
  info "Rebuilding images (no cache)..."
  $DC build --no-cache
fi

info "Starting services: postgres, qdrant, ollama, api, ui..."
$DC up -d --build

# ── Wait for Postgres ─────────────────────────────────────────────────────────
info "Waiting for PostgreSQL to be ready..."
RETRIES=30
until $DC exec -T postgres pg_isready -U "${POSTGRES_USER:-bixso}" -d "${POSTGRES_DB:-bixso_edu}" &>/dev/null; do
  RETRIES=$((RETRIES - 1))
  if [[ $RETRIES -le 0 ]]; then
    error "PostgreSQL did not become ready in time."
    $DC logs postgres | tail -20
    exit 1
  fi
  sleep 2
done
success "PostgreSQL is ready."

# ── Wait for Qdrant ───────────────────────────────────────────────────────────
info "Waiting for Qdrant to be ready..."
RETRIES=30
until curl -sf http://localhost:6333/readyz &>/dev/null; do
  RETRIES=$((RETRIES - 1))
  if [[ $RETRIES -le 0 ]]; then
    error "Qdrant did not become ready in time."
    $DC logs qdrant | tail -20
    exit 1
  fi
  sleep 2
done
success "Qdrant is ready."

# ── Wait for Ollama + pull model ──────────────────────────────────────────────
info "Waiting for Ollama to be ready..."
RETRIES=30
until curl -sf http://localhost:11434 &>/dev/null; do
  RETRIES=$((RETRIES - 1))
  if [[ $RETRIES -le 0 ]]; then
    error "Ollama did not become ready in time."
    $DC logs ollama | tail -20
    exit 1
  fi
  sleep 3
done
success "Ollama is ready."

info "Pulling Ollama model '${OLLAMA_MODEL}' (skipped if already present)..."
$DC exec -T ollama ollama pull "${OLLAMA_MODEL}"
success "Model '${OLLAMA_MODEL}' is ready."

# ── Wait for the FastAPI app ──────────────────────────────────────────────────
info "Waiting for the API to be ready..."
RETRIES=30
until curl -sf http://localhost:8000/health &>/dev/null; do
  RETRIES=$((RETRIES - 1))
  if [[ $RETRIES -le 0 ]]; then
    error "API did not become ready in time."
    $DC logs api | tail -30
    exit 1
  fi
  sleep 3
done
success "API is ready."

# ── Seed / reset the database ─────────────────────────────────────────────────
if [[ "$MODE" == "reset" ]]; then
  info "Resetting database (balances + agent transactions)..."
  $DC exec -T api python -m scripts.init_db --reset
  success "Database reset complete."
else
  info "Seeding database (skips existing rows)..."
  $DC exec -T api python -m scripts.init_db
  success "Database seeded."
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}  ✓ BIXSO Agentic Educator is running!${NC}"
echo ""
echo -e "  ${BOLD}API${NC}          →  http://localhost:8000"
echo -e "  ${BOLD}API Docs${NC}     →  http://localhost:8000/docs"
echo -e "  ${BOLD}Streamlit UI${NC} →  http://localhost:8501"
echo -e "  ${BOLD}Qdrant UI${NC}    →  http://localhost:6333/dashboard"
echo ""
echo -e "  ${CYAN}Logs:${NC}   $DC logs -f api"
echo -e "  ${CYAN}Stop:${NC}   ./start.sh --down"
echo ""
