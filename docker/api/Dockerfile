# ── API / Celery worker image ─────────────────────────────────────────────────
# Single image used for both the FastAPI process and the Celery worker.
# The CMD is overridden per-service in docker-compose.yaml.

FROM python:3.12-slim AS base

# System deps: psycopg2 needs libpq, Docling needs poppler + tesseract,
# OpenCV (via docling-ibm-models) needs libGL + libglib2.0
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        poppler-utils \
        tesseract-ocr \
        curl \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps ───────────────────────────────────────────────────────────────
COPY pyproject.toml uv.lock ./
# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev

# ── Application code ──────────────────────────────────────────────────────────
COPY src/ ./src/
COPY backend/ ./backend/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Make the docseer library importable
ENV PYTHONPATH=/app/src:/app

# Default: run the FastAPI server
# Override in docker-compose.yaml for the Celery worker
CMD ["uv", "run", "uvicorn", "backend.app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--log-level", "info"]
