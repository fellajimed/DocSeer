"""
Ollama HTTP helpers
───────────────────
Used at API startup to pull required models before the LLM / embeddings are
initialised.  All calls go directly to the Ollama REST API so we don't need
a LangChain object yet.

Public surface:
  ensure_models(models, base_url)  — pull any model not already present
"""

from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)

# ── helpers ───────────────────────────────────────────────────────────────────


async def _local_models(base_url: str) -> set[str]:
    """Return the set of model names (tags) already present in Ollama."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            # Each entry looks like {"name": "gemma3:4b-it-q4_K_M", ...}
            return {m["name"] for m in data.get("models", [])}
        except Exception as exc:
            logger.warning("Could not list local Ollama models: %s", exc)
            return set()


async def _pull_model(model: str, base_url: str) -> None:
    """
    Stream-pull *model* from the Ollama registry, logging progress.

    The pull API returns newline-delimited JSON:
      {"status": "pulling manifest"}
      {"status": "pulling <layer>", "total": N, "completed": M}
      {"status": "success"}
    We log a progress line every time the percentage crosses a 10 % boundary
    to keep the log readable without flooding it.
    """
    url = f"{base_url}/api/pull"
    logger.info("Pulling Ollama model '%s' …", model)

    last_pct: int = -1

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST", url, json={"model": model, "stream": True}
        ) as resp:
            resp.raise_for_status()
            async for raw_line in resp.aiter_lines():
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                status: str = data.get("status", "")
                total: int | None = data.get("total")
                completed: int | None = data.get("completed")

                if total and completed:
                    pct = int(completed / total * 100)
                    # Log at most once per 10 % step
                    if pct // 10 > last_pct // 10:
                        logger.info(
                            "  pulling '%s' — %s %d%%", model, status, pct
                        )
                        last_pct = pct
                elif status and status != "success":
                    logger.info("  pulling '%s' — %s", model, status)

    logger.info("Model '%s' is ready.", model)


# ── public API ────────────────────────────────────────────────────────────────


async def ensure_models(models: list[str], base_url: str) -> None:
    """
    For each model in *models*, pull it from Ollama if it is not already
    present locally.  Models are pulled sequentially to avoid saturating
    available bandwidth / disk I/O.

    Errors are logged as warnings rather than raised so a pull failure
    (e.g. no internet in an air-gapped environment) does not crash startup
    when the model was pre-loaded another way.
    """
    if not models:
        return

    present = await _local_models(base_url)
    logger.debug("Ollama local models: %s", present)

    for model in models:
        if model in present:
            logger.info("Model '%s' already present — skipping pull.", model)
            continue
        try:
            await _pull_model(model, base_url)
        except Exception as exc:
            logger.warning(
                "Failed to pull model '%s': %s — continuing anyway.",
                model,
                exc,
            )
