.PHONY: up down run pull-models migrate logs build up-native run-native pull-models-native clean-db

# ── shared helpers ────────────────────────────────────────────────────────────

COMPOSE_NATIVE = docker compose -f docker-compose.yaml -f docker-compose.native-ollama.yml

# ── environment ───────────────────────────────────────────────────────────────

# Copy .env.example on first use
.env:
	cp .env.example .env
	@echo "Created .env from .env.example — edit it before running."

# ── core commands (Dockerized Ollama) ─────────────────────────────────────────

## Build all images
build:
	docker compose build

## Start all backend services (detached)
up: .env
	@mkdir -p $(HOME)/.ollama
	docker compose up -d --wait --build
	@echo "All services healthy."

## Stop and remove containers (keep volumes)
down:
	docker compose down

## Full teardown including volumes (destructive!)
clean:
	docker compose down -v

## Run the TUI (starts backend first if not running)
run: up
	docker compose run --rm --build tui

## Tail logs for all backend services
logs:
	docker compose logs -f --tail=50

# ── native macOS Ollama (Metal GPU) ───────────────────────────────────────────
# Use these targets when Ollama is installed and running on the host.
# Ollama running natively on macOS uses Apple Metal — far faster than Docker.
#
# One-time setup:
#   brew install ollama
#   OLLAMA_HOST=0.0.0.0 ollama serve   # must bind 0.0.0.0, not 127.0.0.1,
#                                       # so Docker containers can reach it via
#                                       # host.docker.internal:11434
#   make pull-models-native

## Pull required models into the native host Ollama
pull-models-native:
	ollama pull $${DOCSEER_LLM_MODEL:-llama3.2:3b}
	ollama pull $${DOCSEER_EMBEDDING_MODEL:-nomic-embed-text}
	@echo "Models ready in native Ollama."

## Start backend services using native macOS Ollama (no Docker Ollama/model-puller)
up-native: .env
	$(COMPOSE_NATIVE) up -d --wait --build
	@echo "All services healthy (native Ollama mode)."

## Run the TUI with native macOS Ollama
run-native: up-native
	$(COMPOSE_NATIVE) run --rm --build tui

## Wipe all paper data (Postgres + ChromaDB + docstore) — keeps Ollama models
clean-db:
	@echo "--- Truncating papers table ---"
	docker exec docseer-postgres psql -U docseer -d docseer -c "TRUNCATE papers CASCADE;"
	@echo "--- Resetting ChromaDB collection ---"
	docker exec docseer-api curl -sf -X DELETE http://chromadb:8000/api/v1/collections/vector_db || true
	docker exec docseer-api curl -sf -X POST http://chromadb:8000/api/v1/collections \
		-H "Content-Type: application/json" -d '{"name":"vector_db"}'
	@echo "--- Clearing docstore ---"
	docker exec docseer-api sh -c "rm -rf /data/docstore/*"
	@echo "All paper data wiped. Ollama models untouched."

# ── database ──────────────────────────────────────────────────────────────────

## Apply Alembic migrations to HEAD
migrate: up
	docker compose exec api uv run alembic upgrade head

## Auto-generate a new Alembic revision (requires description)
# Usage: make revision MSG="add foo column"
revision: up
	docker compose exec api uv run alembic revision --autogenerate -m "$(MSG)"

# ── models ────────────────────────────────────────────────────────────────────

## Pull required Ollama models (LLM + embedding)
pull-models: up
	docker compose exec ollama ollama pull $${DOCSEER_LLM_MODEL:-gemma3:4b-it-q4_K_M}
	docker compose exec ollama ollama pull $${DOCSEER_EMBEDDING_MODEL:-mxbai-embed-large}
	@echo "Models ready."

# ── dev helpers ───────────────────────────────────────────────────────────────

## Open an interactive shell in the API container
shell:
	docker compose exec api bash

## Run the test suite inside the API container
test:
	docker compose exec api uv run pytest tests/ -v

## Show service status
status:
	docker compose ps
