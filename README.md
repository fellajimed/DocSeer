# DocSeer

**DocSeer** is a self-hosted RAG (Retrieval-Augmented Generation) application for research papers. Ingest PDFs, query them in natural language, and explore your library — all running locally via Docker, with no data leaving your machine.

> **Seer**: One who perceives hidden knowledge — interpreting and revealing insights beyond the surface.

[![version](https://img.shields.io/pypi/v/docseer)](https://pypi.org/project/docseer/)
[![tests](https://github.com/fellajimed/docseer/actions/workflows/python-publish.yml/badge.svg)](https://github.com/fellajimed/docseer/actions/workflows/python-publish.yml)

---

## Screenshots

### Chat
![Chat](https://raw.githubusercontent.com/fellajimed/docseer/main/screenshots/chat.png)

The default landing page of the TUI. Chat with your papers using natural language.

### Papers
![Papers](https://raw.githubusercontent.com/fellajimed/docseer/main/screenshots/papers.png)

Browse, filter, and manage your paper library. Search, select, and queue papers for ingestion.

### Conversation
![Conversation](https://raw.githubusercontent.com/fellajimed/docseer/main/screenshots/conversation.png)

A conversation example showing the Q&A flow with retrieved context from ingested papers.

---

## Architecture

| Layer | Technology |
|---|---|
| API | FastAPI (async, SSE streaming) |
| Task queue | Celery + Redis |
| Vector store | ChromaDB |
| Document store | Local file store (parent chunks) |
| Relational DB | PostgreSQL |
| LLM / embeddings | Ollama (fully local) |
| PDF processing | Docling (content) + GROBID (metadata) |
| Metadata import | Zotero Translation Server + BibTeX parser |
| TUI | Textual |
| Monitoring | Flower (Celery dashboard) |

All services run as Docker containers. The only external network call is the initial Ollama model pull, which happens automatically at startup.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with the Compose plugin (`docker compose version`)
- ~10 GB free disk space (models + database volumes)

That's it. No Python, Ollama, or Postgres installation needed on the host — unless you want to use native Ollama for GPU acceleration (see below).

---

## Quick start

### Using the CLI (recommended)

```bash
# Install from PyPI
uv pip install docseer

# Start everything and launch the TUI
docseer            # fully Dockerized (CPU)
docseer --native   # macOS Metal GPU (requires native Ollama on host)
```

Or clone and install in editable mode for development:

```bash
git clone https://github.com/fellajimed/docseer.git
cd docseer
uv pip install -e .
```

One command starts all Docker services (Postgres, Redis, ChromaDB, Ollama, GROBID, Zotero, API, worker, Flower), waits for healthchecks, then opens the Textual TUI. Press `Ctrl+C` or `Ctrl+Q` to quit — services stop automatically.

### Using `make`

```bash
# 1. Clone the repo
git clone https://github.com/fellajimed/docseer.git
cd docseer

# 2. Create your .env (safe to use defaults for local dev)
make .env        # copies .env.example → .env

# 3. Build, start everything, and open the TUI — all in one shot
make run
```

`make run` does the full sequence:
1. Builds the API and worker images
2. Starts all 9 backend services (Postgres, Redis, ChromaDB, Ollama, GROBID, Zotero, API, worker, Flower) and waits for every healthcheck to pass
3. Pulls the configured LLM and embedding models from Ollama if not already present (first boot may take a few minutes)
4. Launches the Textual TUI — chat, manage documents, and tail live container logs

To start only the backend without the TUI:

```bash
make up
```

---

## Running with `make`

DocSeer has two operating modes depending on how Ollama is run. Choose the one that fits your setup.

### Mode 1 — Fully Dockerized (default)

Ollama runs as a Docker container. Works on any OS, no extra setup needed. Inference is CPU-only.

```bash
make up          # build + start all backend services, wait until healthy
make run         # same as above, then launch the TUI
make down        # stop and remove containers (volumes are kept)
```

### Mode 2 — Native macOS Ollama (recommended on Apple Silicon)

Ollama runs on the host using Apple Metal (GPU), giving 10–50× faster inference than the Docker variant. The rest of the stack (Postgres, Redis, ChromaDB, etc.) still runs in Docker.

**One-time setup:**

```bash
# 1. Install and start Ollama (the macOS app binds to all interfaces by default)
brew install ollama
open -a Ollama

# 2. Pull the required models into the native Ollama
make pull-models-native
```

**Day-to-day usage:**

```bash
make up-native   # start backend services (skips the Docker Ollama container)
make run-native  # same as above, then launch the TUI
```

> If Ollama.app is already running, make sure it is configured to listen on
> `0.0.0.0`. You can set `OLLAMA_HOST=0.0.0.0` in your shell or in the
> Ollama.app environment before launching it.

---

## Service URLs

| Service | URL |
|---|---|
| REST API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Flower (Celery monitor) | http://localhost:5555 |
| Ollama | http://localhost:11434 |
| GROBID | http://localhost:8070 |

---

## Configuration

All settings are environment variables prefixed with `DOCSEER_`. Copy `.env.example` to `.env` and adjust as needed.

```bash
cp .env.example .env
```

You can also pass a YAML config file at runtime with the `-c` / `--config` flag. Short names (without the `DOCSEER_` prefix) are automatically expanded:

```yaml
# example config
llm_model: qwen3.5:4b
embedding_model: nomic-embed-text
retriever_topk: 10
chat_num_ctx: 32000
```

### Key settings

| Variable | Default | Description |
|---|---|---|
| `DOCSEER_LLM_MODEL` | `qwen3.5:4b` | Ollama model used for chat |
| `DOCSEER_EMBEDDING_MODEL` | `nomic-embed-text` | Ollama model used for embeddings |
| `DOCSEER_OLLAMA_PULL_ON_STARTUP` | `true` | Pull models at startup if not present locally |
| `DOCSEER_RETRIEVER_TOPK` | `5` | Number of chunks retrieved per query |
| `DOCSEER_RERANKER_MODEL` | `ms-marco-MultiBERT-L-12` | FlashRank reranker model |
| `DOCSEER_CHAT_NUM_CTX` | `20000` | KV-cache context window (tokens) |
| `DOCSEER_CHAT_NUM_PREDICT` | `4096` | Max tokens per response |

To use a different LLM:

```bash
# in your .env
DOCSEER_LLM_MODEL=llama3.2
```

> **Important:** do not mix embedding models across an existing database.
> `nomic-embed-text` produces 768-dimensional vectors. Switching models
> requires wiping and re-ingesting all papers (`make clean-db`).

Set `DOCSEER_OLLAMA_PULL_ON_STARTUP=false` if you pre-pull models yourself or work in an air-gapped environment.

---

## All `make` commands

### Backend

| Command | Description |
|---|---|
| `make up` | Build + start all backend services (Dockerized Ollama), wait until healthy |
| `make up-native` | Same, but skips Docker Ollama — uses native host Ollama instead |
| `make down` | Stop and remove containers (volumes are kept) |
| `make clean` | Full teardown including all volumes — **destructive** |
| `make clean-db` | Wipe paper data (Postgres + ChromaDB + docstore) while keeping Ollama models |
| `make logs` | Tail logs for all backend services |
| `make status` | Show container status (`docker compose ps`) |
| `make build` | Build images without starting |

### TUI

| Command | Description |
|---|---|
| `make run` | Start backend (Dockerized Ollama) then launch the TUI |
| `make run-native` | Start backend (native Ollama) then launch the TUI |

### Models

| Command | Description |
|---|---|
| `make pull-models` | Pull LLM + embedding models into the Docker Ollama container |
| `make pull-models-native` | Pull LLM + embedding models into the native host Ollama |

### Development

| Command | Description |
|---|---|
| `make migrate` | Apply Alembic migrations to HEAD |
| `make shell` | Open a bash shell inside the API container |
| `make test` | Run the pytest suite inside the API container |

---

## CLI reference

Once installed (`uv pip install -e .` or `pip install docseer`), the `docseer` command manages the full stack.

| Command | Description |
|---|---|
| `docseer` | Start services, launch TUI, then stop on exit (default) |
| `docseer run` | Same as above |
| `docseer run --keep` | Keep services running after TUI exits |
| `docseer run --native` | Use native macOS Ollama (Metal GPU) |
| `docseer run --no-wait` | Don't wait for healthchecks (faster startup) |
| `docseer run --rebuild` | Force rebuild of Docker images |
| `docseer run -c config.yaml` | Start with YAML config overrides |
| `docseer start` | Start all Docker services in background |
| `docseer stop` | Stop all Docker services |
| `docseer clean` | Stop services and wipe all volumes |
| `docseer tui` | Launch TUI only (services must already be running) |
| `docseer ingest <src> [<src> ...]` | Ingest papers — URLs, PDF paths, or `.bib` files |
| `docseer ingest --no-trigger <url>` | Save URL metadata only, skip PDF ingestion |
| `docseer --version` | Show version |

---

## TUI keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl+C` / `Ctrl+Q` | Quit |
| `Ctrl+T` | Chat tab |
| `Ctrl+F` | Papers tab |
| `Ctrl+L` | Logs tab |
| `Ctrl+S` | DocSeer Settings (LLM model, embedding model, theme) |
| `Ctrl+P` | Textual Command Palette |
| `Alt+P` | Filter Papers (open paper picker) |
| `Alt+M` | Open Macro Selector |

**Chat tab:**

| Key | Action |
|---|---|
| `Ctrl+J` / `Ctrl+M` / `Ctrl+Enter` | Send message |
| `Tab` | Auto-complete `/macro` name |
| `<char>` after `/` | Opens Macro Selector modal |

**Available macros:**

| Macro | Action |
|---|---|
| `/papers` | Open paper filter picker |
| `/summarize` | Structured summary of selected papers |
| `/extract` | Extract contributions, methodology, results |
| `/synthesize` | Cross-paper synthesis and insights |
| `/compare` | Side-by-side comparison of papers |
| `/critique` | Critical analysis of papers |

Type `/<char>` in the chat input to open the Macro Selector modal, or type the full macro name and press `Enter`.

**Papers tab:**

| Key | Action |
|---|---|
| Type a path or URL | Add a paper (PDF, `.bib`, or any URL) |
| `Tab` → `Enter` | Select/deselect papers for the chat filter |

---

## REST API overview

The full interactive documentation is available at **http://localhost:8000/docs** once the stack is running.

### Papers

| Method | Path | Description |
|---|---|---|
| `GET` | `/papers/` | List all papers |
| `POST` | `/papers/` | Add a paper and queue ingestion |
| `GET` | `/papers/{id}` | Get a paper by ID |
| `PUT` | `/papers/{id}` | Update paper metadata |
| `DELETE` | `/papers/{id}` | Delete paper and its embeddings |
| `POST` | `/papers/import-bibtex` | Import papers from a BibTeX string |
| `POST` | `/papers/import-url` | Import metadata via Zotero Translation Server |
| `POST` | `/papers/{id}/ingest` | (Re-)trigger PDF ingestion |

### Chat

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat/stream` | SSE stream — yields `thinking`, `response`, `done`, `error` events |
| `POST` | `/chat/invoke` | Blocking single-turn response |
| `GET` | `/chat/history` | Return conversation history |
| `DELETE` | `/chat/history` | Clear conversation history |

### Tasks

| Method | Path | Description |
|---|---|---|
| `GET` | `/tasks/{task_id}` | Poll a Celery task (PENDING / STARTED / SUCCESS / FAILURE) |

---

## Pipeline

### Ingestion

```
  PDF / URL
      │
      ▼
  ┌─────────────┐
  │ get_file_bytes()│
  └──────┬──────┘
         │  doc_bytes
         ▼
  ┌──────────────┐     ┌──────────────────┐
  │   GROBID     │     │     Docling      │
  │  (metadata)  │     │ (PDF → Markdown) │
  └──────┬───────┘     └────────┬─────────┘
         │                      │
         ▼                      ▼
     metadata             page_content
         │                      │
         └──────────┬───────────┘
                    ▼
          ┌─────────────────┐
          │ MarkdownHeader  │
          │ TextSplitter    │  parent chunks (by heading)
          └────────┬────────┘
                   │
          ┌─────────────────┐
          │RecursiveCharText│  child chunks (~800 chars, 80 overlap)
          │ TextSplitter    │
          └────────┬────────┘
                   │
         ┌─────────┴──────────┐
         ▼                    ▼
  ┌──────────────┐   ┌────────────────┐
  │   Ollama     │   │LocalFileStore  │
  │  nomic-embed │   │(parent chunks) │
  └──────┬───────┘   └────────────────┘
         │
         ▼
  ┌──────────────┐
  │   ChromaDB   │   child chunk vectors + metadata
  └──────────────┘
```

### Retrieval

```
  User query
      │
      ▼
  ┌──────────────┐
  │ Ollama embed │   embed query → vector
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │   ChromaDB   │   cosine similarity search (optionally filtered by paper_ids)
  └──────┬───────┘
         │  top-k child chunks (contain parent_id references)
         ▼
  ┌──────────────┐
  │LocalFileStore│   resolve child → parent chunk (full section context)
  └──────┬───────┘
         │  parent chunk text
         ▼
  ┌──────────────┐
  │  Ollama LLM  │   qwen3.5:4b + retrieved context → answer
  └──────┬───────┘
         │  SSE stream (thinking + response tokens)
         ▼
       TUI chat
```

For the retrieval step, `paper_ids` can optionally be passed to restrict the search to specific papers. This is how the paper filter in the Chat tab works.

### Chunking strategy

```
  Parent chunk  ───→  Child chunk   ───→  Embedding in ChromaDB
  (heading section)     (800 chars overlap)
       │
       └── stored in LocalFileStore
       │
       └── 120 char overlap carried from previous parent for continuity
```

During retrieval, child chunks are matched by similarity, then resolved to their parent for richer context.

---

## Ingestion pipeline

1. A paper is created via `POST /papers/` (with `source_path`) or `POST /papers/import-url`.
2. Celery picks up the `ingest` task on the `ingest` queue.
3. The worker converts the PDF to Markdown using **Docling**, extracts metadata via **GROBID**, chunks the content with a parent-child chunker, and stores vectors in **ChromaDB** + parent chunks in the local docstore.
4. Ingestion is **idempotent** — re-ingesting a paper first purges its existing vectors and chunks before rebuilding them.
5. Poll `GET /tasks/{task_id}` or watch Flower at http://localhost:5555 to track progress.

---

## Development

```bash
# Install all dependencies (including dev) locally with uv
uv sync

# Run tests
uv run pytest tests/ -v

# Run the API locally (requires running infra services)
uv run uvicorn backend.app.main:app --reload

# Run a Celery worker locally
uv run celery -A backend.app.celery_app.celery_app worker --loglevel=info --queues=ingest
```

---

## License

MIT License
