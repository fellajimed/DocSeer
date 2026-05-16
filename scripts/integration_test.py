#!/usr/bin/env python3
"""
DocSeer end-to-end integration test
====================================
Tests the full pipeline against a running Docker Compose stack:

  1. POST /papers/          → paper created, Celery task queued
  2. Poll GET /tasks/{id}   → wait until SUCCESS (ingest done)
  3. GET  /papers/{id}      → verify status=done, chunk_count > 0
  4. POST /chat/stream      → consume SSE, verify a grounded answer arrives
  5. DELETE /papers/{id}    → cleanup

Usage:
    uv run python scripts/integration_test.py

Optional env vars:
    DOCSEER_API_URL   default: http://localhost:8000
    PAPER_URL         arXiv PDF URL to ingest (default: attention-is-all-you-need)
    CHAT_QUERY        question to ask after ingestion
    POLL_TIMEOUT      seconds to wait for ingestion (default: 300)
    POLL_INTERVAL     seconds between polls (default: 5)
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

# ── Config ────────────────────────────────────────────────────────────────────

API_URL = os.getenv("DOCSEER_API_URL", "http://localhost:8000")
PAPER_URL = os.getenv("PAPER_URL", "https://arxiv.org/pdf/1706.03762")
CHAT_QUERY = os.getenv(
    "CHAT_QUERY",
    "What is the main contribution of this paper? Summarise the architecture.",
)
POLL_TIMEOUT = int(os.getenv("POLL_TIMEOUT", "300"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))

# ── ANSI helpers ──────────────────────────────────────────────────────────────

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"{GREEN}✓{RESET}  {msg}")


def err(msg: str) -> None:
    print(f"{RED}✗{RESET}  {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"{CYAN}→{RESET}  {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠{RESET}  {msg}")


def step(n: int, total: int, msg: str) -> None:
    print(f"\n{BOLD}[{n}/{total}]{RESET} {msg}")


def die(msg: str) -> None:
    err(msg)
    sys.exit(1)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _check(r: httpx.Response, *, expect: int, label: str) -> dict:
    if r.status_code != expect:
        die(f"{label} — HTTP {r.status_code}: {r.text[:400]}")
    return r.json()


def poll_task(client: httpx.Client, task_id: str) -> dict | None:
    """Block until the Celery task reaches a terminal state, return final payload."""
    deadline = time.monotonic() + POLL_TIMEOUT
    last_step = ""
    while time.monotonic() < deadline:
        r = client.get(f"{API_URL}/tasks/{task_id}")
        data = _check(r, expect=200, label="GET /tasks/{task_id}")
        state = data["state"]

        step_info = (data.get("progress") or {}).get("step", "")
        if step_info and step_info != last_step:
            info(f"  worker step: {YELLOW}{step_info}{RESET}")
            last_step = step_info

        if state == "SUCCESS":
            return data
        if state in ("FAILURE", "RETRY", "REVOKED"):
            die(
                f"Task {task_id} ended with state={state}: {data.get('error')}"
            )

        time.sleep(POLL_INTERVAL)

    die(f"Timed out after {POLL_TIMEOUT}s waiting for task {task_id}")


def consume_sse_stream(client: httpx.Client, query: str) -> tuple[str, str]:
    """POST /chat/stream and collect all SSE events. Returns (thinking, response)."""
    thinking_parts: list[str] = []
    response_parts: list[str] = []

    with client.stream(
        "POST",
        f"{API_URL}/chat/stream",
        json={"query": query, "think_mode": False},
        timeout=120,
    ) as r:
        if r.status_code != 200:
            r.read()
            die(f"POST /chat/stream — HTTP {r.status_code}: {r.text[:400]}")

        for raw_line in r.iter_lines():
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            payload_str = line[len("data:") :].strip()
            try:
                event = json.loads(payload_str)
            except json.JSONDecodeError:
                warn(f"  malformed SSE line: {line!r}")
                continue

            etype = event.get("type")
            if etype == "thinking":
                thinking_parts.append(event.get("content", ""))
            elif etype == "response":
                response_parts.append(event.get("content", ""))
                # Print tokens live
                print(event.get("content", ""), end="", flush=True)
            elif etype == "error":
                print()
                die(f"SSE error event: {event.get('content')}")
            elif etype == "done":
                print()  # newline after streaming
                break

    return "".join(thinking_parts), "".join(response_parts)


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    TOTAL = 5

    print(f"\n{BOLD}DocSeer Integration Test{RESET}")
    print(f"{DIM}API:   {API_URL}")
    print(f"Paper: {PAPER_URL}")
    print(f"Query: {CHAT_QUERY}{RESET}\n")

    with httpx.Client(timeout=30) as client:
        # ── 1. Health check ───────────────────────────────────────────────────
        step(1, TOTAL, "Health check")
        r = client.get(f"{API_URL}/papers/")
        if r.status_code != 200:
            die(f"API not reachable at {API_URL}: HTTP {r.status_code}")
        ok(f"API reachable — {len(r.json())} existing paper(s) in DB")

        # ── 2. Add paper ──────────────────────────────────────────────────────
        step(2, TOTAL, f"Adding paper: {PAPER_URL}")
        r = client.post(f"{API_URL}/papers/", json={"source_path": PAPER_URL})
        data = _check(r, expect=202, label="POST /papers/")
        paper_id = str(data["paper_id"])
        task_id = data["task_id"]
        info(f"paper_id = {paper_id}")
        info(f"task_id  = {task_id}")
        ok("Paper created, ingest task queued")

        # ── 3. Wait for ingestion ─────────────────────────────────────────────
        step(3, TOTAL, f"Waiting for ingestion (timeout={POLL_TIMEOUT}s)...")
        t0 = time.monotonic()
        final = poll_task(client, task_id) or dict()
        elapsed = time.monotonic() - t0
        chunk_count = (final.get("result") or {}).get("chunk_count", "?")
        ok(f"Ingest complete in {elapsed:.1f}s — {chunk_count} chunks")

        # ── 3b. Verify paper record ───────────────────────────────────────────
        r = client.get(f"{API_URL}/papers/{paper_id}")
        paper = _check(r, expect=200, label="GET /papers/{id}")
        status = paper["status"]
        db_chunks = paper["chunk_count"]
        if status != "done":
            die(
                f"Paper status is {status!r} (expected 'done'). error: {paper.get('error_message')}"
            )
        if not db_chunks or db_chunks < 1:
            die(f"chunk_count={db_chunks} — nothing was embedded")
        ok(
            f"Paper status=done, chunk_count={db_chunks}, title={paper.get('title')!r}"
        )

        # ── 4. Chat ───────────────────────────────────────────────────────────
        step(4, TOTAL, "Streaming chat query...")
        info(f"Query: {CYAN}{CHAT_QUERY}{RESET}")
        print(f"\n{DIM}--- response stream start ---{RESET}")

        thinking, response = consume_sse_stream(client, CHAT_QUERY)

        print(f"{DIM}--- response stream end   ---{RESET}\n")

        if not response.strip():
            die("Got an empty response from /chat/stream")

        ok(f"Received {len(response)} chars of response text")
        if thinking:
            ok(f"Received {len(thinking)} chars of thinking tokens")

        # Basic grounding check: the paper is about "transformers" / "attention"
        lower = response.lower()
        keywords = ["attention", "transformer", "encoder", "decoder", "model"]
        matched = [kw for kw in keywords if kw in lower]
        if matched:
            ok(f"Response contains expected keywords: {matched}")
        else:
            warn(
                "Response did not contain expected domain keywords — check manually"
            )

        # ── 5. Cleanup ────────────────────────────────────────────────────────
        step(5, TOTAL, "Cleaning up (DELETE paper + embeddings)...")
        r = client.delete(f"{API_URL}/papers/{paper_id}", timeout=30)
        if r.status_code != 204:
            warn(f"DELETE returned HTTP {r.status_code} (non-fatal)")
        else:
            ok("Paper and embeddings deleted")

    print(f"\n{BOLD}{GREEN}All steps passed.{RESET}\n")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
