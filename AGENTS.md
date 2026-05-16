# DocSeer — agent instructions

## Two operating modes
- **Docker Ollama (default):** `make up` / `make run` — CPU-only inference in Docker
- **Native macOS Ollama (recommended):** `make up-native` / `make run-native` — Metal GPU, 10–50× faster. Requires `OLLAMA_HOST=0.0.0.0 ollama serve` on host first.
- Both include `--build`, so any code change is always baked into images.

## Key commands
| Command | Action |
|---|---|
| `make up` / `make up-native` | Build + start all backend services, wait for healthchecks |
| `make run` / `make run-native` | Same + launch TUI |
| `make down` | Stop containers (keeps volumes) |
| `make clean-db` | Wipe paper data, keep Ollama models |
| `make test` | `docker compose exec api uv run pytest tests/ -v` |
| `make shell` | Open bash in API container |
| `make logs` | Tail all backend container logs |

## Architecture
- **`src/docseer/`** — pure domain library (chunkers, retrievers, databases, converters). No FastAPI/Celery imports.
- **`backend/app/`** — application layer (FastAPI routers, Celery tasks, SQLAlchemy models, pydantic schemas).
- **`ui/terminal/`** — Textual TUI. Entrypoint: `main.py`. Communicates with API via HTTP (not in-process).
- Both `backend/app/` and `ui/terminal/` import from `src/docseer/`.

## Textual 6.10.0 quirks
- **BINDINGS with `priority=True`** must use `Binding` class, not tuples:
  ```python
  from textual.binding import Binding
  BINDINGS = [Binding("ctrl+t", "go_chat", "Chat", priority=True)]
  ```
- **No `@media` CSS support** — use fixed `grid-size` or Python-level resize handling instead.
- **`push_screen_wait` requires a worker** — use `push_screen(screen, callback)` from event handlers instead.
- **`Ctrl+I` sends Tab keycode** — avoid for bindings; use `Ctrl+T` for tab switching.
- **`Ctrl+Space` unreliable** in terminals — prefer `Alt` combinations for actions.
- Footer auto-shows `Binding.description` of all app-level bindings.

## CI / pre-commit
- `.pre-commit-config.yaml`: ruff (lint+format) + `ty check src/` typecheck.
- Order: ruff → ruff-format → ty (typecheck).
- Run with `pre-commit run --all-files` or let CI enforce it.

## Testing
- `pytest asyncio_mode = "auto"` in `pyproject.toml`.
- Tests live under `tests/unit/`, `tests/api/`, `tests/integration/`.
- Integration tests (`tests/integration/test_converter.py`) use a real PDF fixture in `tests/fixtures/` and are marked `@pytest.mark.slow`.
- Run inside the API container: `make test` or `docker compose exec api uv run pytest tests/ -v`.

## Docker mounts
- **TUI** and **worker** both mount `$HOME:$HOME:ro` so host file paths (PDFs, `.bib` files) resolve at the same absolute path inside containers.
- Docker socket (`/var/run/docker.sock`) mounted in TUI so `docker logs` works.

## Default models
- LLM: `qwen3.5:4b` (set in `.env` via `DOCSEER_LLM_MODEL`)
- Embedder: `nomic-embed-text` (set in `.env` via `DOCSEER_EMBEDDING_MODEL`)
- Mixing embedding models across an existing DB requires `make clean-db` and re-ingest.

## Flower (Celery dashboard)
- URL: http://localhost:5555
- Auth disabled by default. Set `FLOWER_USER` / `FLOWER_PASSWORD` in `.env` to enable.

## TUI global keybindings
| Key | Action |
|---|---|
| `Ctrl+T` | Chat tab |
| `Ctrl+F` | Papers tab |
| `Ctrl+L` | Logs tab |
| `Ctrl+S` | DocSeer Settings |
| `Ctrl+P` | Textual Command Palette |
| `Alt+P` | Filter Papers (open paper picker) |

## BibTeX import
- Type a `.bib` file path in the Papers tab input bar → `BibtexImportModal` opens with search + select/deselect all.
- Selected entries are queued for ingestion (if they have a `file` or `url` field); deselected entries are saved as metadata-only.
- Uses `bibtexparser` to parse client-side in the TUI.

## uv Python setup
- All deps managed with `uv sync`. The `uv` CLI is available in all Docker contexts.
- `uv run <script>` replaces plain `python <script>` in containers.
