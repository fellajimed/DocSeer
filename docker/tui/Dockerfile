FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
COPY ui/terminal/ ./ui/terminal/

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gnupg \
        lsb-release \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
       -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
       https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY --from=build /app/ui/terminal ./ui/terminal
COPY src/docseer/prompts/ ./src/docseer/prompts/

ENV PYTHONPATH=/app/ui/terminal:/app/src
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uv", "run", "python", "ui/terminal/main.py"]
