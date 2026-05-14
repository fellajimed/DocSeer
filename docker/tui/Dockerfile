# ── TUI image ─────────────────────────────────────────────────────────────────
# Runs the Textual terminal UI.
# Requires /var/run/docker.sock mounted so DockerLogsWidget can tail
# container logs via the Docker CLI.

FROM python:3.12-slim

# Docker CLI — needed so the TUI can run `docker logs -f <container>`
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

# ── Python deps (TUI subset only — no ML models needed) ───────────────────────
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev

# ── TUI source ────────────────────────────────────────────────────────────────
COPY ui/terminal/ ./ui/terminal/

ENV PYTHONPATH=/app/ui/terminal

# tty is required for Textual; docker-compose sets `tty: true`
CMD ["uv", "run", "python", "ui/terminal/main.py"]
