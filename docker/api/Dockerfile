FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        poppler-utils \
        tesseract-ocr \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
COPY src/ ./src/
COPY backend/ ./backend/
COPY alembic/ ./alembic/
COPY alembic.ini ./

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        poppler-utils \
        tesseract-ocr \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY --from=build /app/src ./src
COPY --from=build /app/backend ./backend
COPY --from=build /app/alembic ./alembic
COPY --from=build /app/alembic.ini ./

ENV PYTHONPATH=/app/src:/app
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "backend.app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--log-level", "info"]
