#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
DocSeer Pipeline Benchmark
===========================
Measures end-to-end latency at each stage of the full pipeline
against a running stack.

Stages measured:
  1. API health        — GET /health round-trip
  2. Paper submit      — POST /papers/ round-trip
  3. Ingest pipeline   — per-step timing polled from GET /tasks/{id}:
       loading          DB fetch + validation
       converting       Docling PDF → Markdown (+ GROBID)
       chunking         Parent-child text splitting
       embedding        OllamaEmbeddings → ChromaDB write + LocalFileStore
  4. Chat (no-think)   — POST /chat/stream with think_mode=False:
       server latency   request → meta (before retrieval)
       retrieval+prefill meta → first token
       TTFT             request → first token
       generation       first token → done
       total            request → done
  5. Chat (think)      — same query with think_mode=True; includes thinking
                         token count and thinking latency breakdown

Usage:
    uv run python scripts/benchmark.py

Env vars:
    DOCSEER_API_URL   default: http://localhost:8000
    PAPER_URL         PDF to ingest (default: Attention Is All You Need)
    CHAT_QUERY        question to ask after ingest
    POLL_TIMEOUT      max seconds to wait for ingest  (default: 600)
    POLL_INTERVAL     seconds between task polls      (default: 2)
    KEEP_PAPER        set to "1" to skip DELETE at end
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
    "What is the main contribution of this paper? Summarise the key architecture.",
)
POLL_TIMEOUT = int(os.getenv("POLL_TIMEOUT", "600"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "2"))
KEEP_PAPER = os.getenv("KEEP_PAPER", "0") == "1"

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


def die(msg: str) -> None:
    err(msg)
    sys.exit(1)


def hdr(msg: str) -> None:
    print(f"\n{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}  {msg}{RESET}")
    print(f"{BOLD}{'─' * 60}{RESET}")


# ── Benchmark result store ────────────────────────────────────────────────────

results: dict[str, float] = {}  # label → seconds


def record(label: str, seconds: float) -> None:
    results[label] = seconds


def _fmt(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    return f"{seconds:.2f} s"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _check(r: httpx.Response, *, expect: int, label: str) -> dict:
    if r.status_code != expect:
        die(f"{label} — HTTP {r.status_code}: {r.text[:400]}")
    return r.json()


def benchmark_health(client: httpx.Client) -> None:
    hdr("1 / 5  API health round-trip")
    t0 = time.monotonic()
    r = client.get(f"{API_URL}/health")
    elapsed = time.monotonic() - t0
    if r.status_code != 200:
        die(f"API not reachable at {API_URL}: HTTP {r.status_code}")
    record("api_health", elapsed)
    ok(f"GET /health → {r.json().get('status', '?')}  [{_fmt(elapsed)}]")


def benchmark_submit(client: httpx.Client) -> tuple[str, str, bool]:
    """
    POST /papers/ and return (paper_id, task_id, already_existed).
    - 202 → freshly queued
    - 200 with status=already_ingested → paper was in DB already; skip ingest poll
    """
    hdr("2 / 5  Paper submission")
    info(f"URL: {PAPER_URL}")
    t0 = time.monotonic()
    r = client.post(f"{API_URL}/papers/", json={"source_path": PAPER_URL})
    elapsed = time.monotonic() - t0

    if r.status_code not in (200, 202):
        die(f"POST /papers/ — HTTP {r.status_code}: {r.text[:400]}")

    data = r.json()
    record("paper_submit", elapsed)
    paper_id = str(data["paper_id"])
    task_id = data.get("task_id", "")
    already_exists = data.get("status") == "already_ingested"

    if already_exists:
        ok(f"Paper already in DB — skipping ingest  [{_fmt(elapsed)}]")
    else:
        ok(f"POST /papers/ → queued  [{_fmt(elapsed)}]")
    info(f"paper_id = {paper_id}")
    if task_id:
        info(f"task_id  = {task_id}")
    return paper_id, task_id, already_exists


# Canonical order Celery steps appear in
_STEP_ORDER = ["loading", "converting", "chunking", "embedding"]


def benchmark_ingest(client: httpx.Client, task_id: str) -> int:
    """
    Poll GET /tasks/{task_id} until SUCCESS.
    Records per-step durations and total ingest time.
    Returns chunk_count from task result.

    NOTE: "loading" completes in <1s (DB fetch) so it is almost always done
    before the first poll fires.  We synthesise its duration as the time
    between t_ingest_start and the first observed step transition.
    """
    hdr("3 / 5  Ingest pipeline (polling every {:.0f}s)".format(POLL_INTERVAL))

    t_ingest_start = time.monotonic()
    deadline = t_ingest_start + POLL_TIMEOUT

    # step_name → monotonic timestamp when that step was FIRST observed
    step_first_seen: dict[str, float] = {}

    while time.monotonic() < deadline:
        r = client.get(f"{API_URL}/tasks/{task_id}")
        data = _check(r, expect=200, label="GET /tasks/{task_id}")
        state = data["state"]
        now = time.monotonic()

        step = (data.get("progress") or {}).get("step", "")
        if step and step not in step_first_seen:
            step_first_seen[step] = now
            info(
                f"  [{_fmt(now - t_ingest_start):>8}]  step: {YELLOW}{step}{RESET}"
            )

        if state == "SUCCESS":
            t_done = now
            chunk_count = (data.get("result") or {}).get("chunk_count", 0)

            # "loading" is never seen (done in <1 poll interval).
            # Treat the gap from t_ingest_start to the first observed step
            # as an upper-bound for loading + queue wait.
            first_seen_t = (
                min(step_first_seen.values()) if step_first_seen else t_done
            )
            record("ingest_loading", first_seen_t - t_ingest_start)

            # Per-step durations between consecutive first-seen timestamps
            all_steps = [s for s in _STEP_ORDER if s in step_first_seen]
            for i, s in enumerate(all_steps):
                t_start = step_first_seen[s]
                t_end = (
                    step_first_seen[all_steps[i + 1]]
                    if i + 1 < len(all_steps)
                    else t_done
                )
                duration = t_end - t_start
                record(f"ingest_{s}", duration)
                ok(f"  {s:<12} {_fmt(duration)}")

            total = t_done - t_ingest_start
            record("ingest_total", total)
            ok(f"  {'TOTAL':<12} {_fmt(total)}  ({chunk_count} chunks)")
            return chunk_count

        if state in ("FAILURE", "RETRY", "REVOKED"):
            die(
                f"Task {task_id} ended with state={state}: {data.get('error')}"
            )

        time.sleep(POLL_INTERVAL)

    die(f"Timed out after {POLL_TIMEOUT}s waiting for ingest task")
    return 0  # unreachable


def benchmark_chat(
    client: httpx.Client, *, think_mode: bool, step: str
) -> None:
    """
    POST /chat/stream and measure:
      - t_meta         → server latency (meta fires BEFORE retrieval)
      - t_think_start  → when first thinking token arrived (think mode only)
      - t_first_token  → retrieval + LLM prefill time (meta → first response token)
      - chat_ttft      → total time to first token (request → first response token)
      - chat_generation → generation time (first response token → done)
      - chat_total     → full round-trip (request → done)
    """
    mode = "think" if think_mode else "no_think"
    label = "think" if think_mode else "no-think"
    hdr(f"{step}  Chat ({label}): retrieval · TTFT · generation")
    info(f"Query: {CYAN}{CHAT_QUERY}{RESET}")
    info(f"think_mode: {think_mode}\n")

    t_request = time.monotonic()
    t_meta: float | None = None
    t_think_start: float | None = None
    t_first_token: float | None = None
    t_done_event: float | None = None
    response_parts: list[str] = []
    thinking_parts: list[str] = []
    token_count = 0
    think_tok_count = 0

    with client.stream(
        "POST",
        f"{API_URL}/chat/stream",
        json={"query": CHAT_QUERY, "think_mode": think_mode},
        timeout=300,
    ) as r:
        if r.status_code != 200:
            r.read()
            die(f"POST /chat/stream — HTTP {r.status_code}: {r.text[:400]}")

        print(f"{DIM}{'─' * 60}{RESET}")
        for raw_line in r.iter_lines():
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue

            payload_str = line[len("data:") :].strip()
            try:
                event = json.loads(payload_str)
            except json.JSONDecodeError:
                warn(f"malformed SSE line: {line!r}")
                continue

            etype = event.get("type")
            content = event.get("content", "")
            now = time.monotonic()

            if etype == "meta":
                if t_meta is None:
                    t_meta = now
                    info(f"  [stream-start  {_fmt(t_meta - t_request):>8}]")
                else:
                    info(f"  [{content:<20} {_fmt(now - t_request):>8}]")

            elif etype == "thinking":
                if t_think_start is None:
                    t_think_start = now
                thinking_parts.append(content)
                think_tok_count += 1

            elif etype == "response":
                if t_first_token is None:
                    t_first_token = now
                response_parts.append(content)
                token_count += 1
                print(content, end="", flush=True)

            elif etype == "error":
                print()
                die(f"SSE error: {content}")

            elif etype == "done":
                t_done_event = now
                print()
                break

        print(f"{DIM}{'─' * 60}{RESET}\n")

    # ── Record timings ────────────────────────────────────────────────────────
    if t_meta is not None:
        record(f"chat_{mode}_server_latency", t_meta - t_request)

    if t_think_start is not None:
        record(f"chat_{mode}_think_start", t_think_start - t_request)

    if t_first_token is not None:
        record(f"chat_{mode}_ttft", t_first_token - t_request)
        if t_meta is not None:
            record(f"chat_{mode}_retrieval", t_first_token - t_meta)

    if t_first_token is not None and t_done_event is not None:
        record(f"chat_{mode}_generation", t_done_event - t_first_token)

    if t_done_event is not None:
        record(f"chat_{mode}_total", t_done_event - t_request)

    full_response = "".join(response_parts)
    if not full_response.strip():
        die(
            f"Received empty response from /chat/stream (think_mode={think_mode})"
        )

    ok(f"Response: {len(full_response)} chars, ~{token_count} SSE tokens")
    if think_tok_count:
        thinking_text = "".join(thinking_parts)
        ok(
            f"Thinking: {len(thinking_text)} chars, ~{think_tok_count} SSE tokens"
        )


def cleanup(client: httpx.Client, paper_id: str) -> None:
    hdr("Cleanup")
    if KEEP_PAPER:
        warn("KEEP_PAPER=1 — skipping DELETE")
        return
    r = client.delete(f"{API_URL}/papers/{paper_id}", timeout=30)
    if r.status_code == 204:
        ok(f"Deleted paper {paper_id}")
    else:
        warn(f"DELETE returned HTTP {r.status_code} (non-fatal)")


def print_summary() -> None:
    hdr("Benchmark Summary")

    rows = [
        ("api_health", "API health round-trip"),
        ("paper_submit", "Paper submission (POST /papers/)"),
        (
            "ingest_loading",
            "  Ingest › loading   (queue wait + DB fetch) [≤ poll interval]",
        ),
        ("ingest_converting", "  Ingest › converting (PDF → Markdown)"),
        ("ingest_chunking", "  Ingest › chunking   (parent-child split)"),
        ("ingest_embedding", "  Ingest › embedding  (OllamaEmbed → ChromaDB)"),
        ("ingest_total", "Ingest total"),
        # ── no-think ──────────────────────────────────────────────────────────
        (
            "chat_no_think_server_latency",
            "Chat (no-think) › server latency    (request → stream-start)",
        ),
        (
            "chat_no_think_retrieval",
            "Chat (no-think) › retrieval+prefill  (stream-start → 1st token)",
        ),
        (
            "chat_no_think_ttft",
            "Chat (no-think) › TTFT               (request → 1st token)",
        ),
        (
            "chat_no_think_generation",
            "Chat (no-think) › generation         (1st token → done)",
        ),
        ("chat_no_think_total", "Chat (no-think) total"),
        # ── think ─────────────────────────────────────────────────────────────
        (
            "chat_think_server_latency",
            "Chat (think)    › server latency    (request → stream-start)",
        ),
        (
            "chat_think_think_start",
            "Chat (think)    › think start       (request → 1st think token)",
        ),
        (
            "chat_think_retrieval",
            "Chat (think)    › retrieval+prefill  (stream-start → 1st token)",
        ),
        (
            "chat_think_ttft",
            "Chat (think)    › TTFT               (request → 1st resp token)",
        ),
        (
            "chat_think_generation",
            "Chat (think)    › generation         (1st token → done)",
        ),
        ("chat_think_total", "Chat (think)    total"),
    ]

    label_w = max(len(label) for _, label in rows) + 2
    print(f"\n  {'Metric':<{label_w}}  {'Time':>10}")
    print(f"  {'─' * label_w}  {'─' * 10}")
    for key, label in rows:
        if key in results:
            print(f"  {label:<{label_w}}  {_fmt(results[key]):>10}")
        else:
            print(f"  {label:<{label_w}}  {'—':>10}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"\n{BOLD}DocSeer Pipeline Benchmark{RESET}")
    print(f"{DIM}API:   {API_URL}")
    print(f"Paper: {PAPER_URL}")
    print(f"Query: {CHAT_QUERY}{RESET}")

    with httpx.Client(timeout=30) as client:
        benchmark_health(client)
        paper_id, task_id, already_exists = benchmark_submit(client)
        if already_exists:
            warn("Ingest benchmark skipped (paper already in DB)")
        else:
            benchmark_ingest(client, task_id)
        benchmark_chat(client, think_mode=False, step="4 / 5")
        benchmark_chat(client, think_mode=True, step="5 / 5")
        cleanup(client, paper_id)

    print_summary()
    print(f"{BOLD}{GREEN}Benchmark complete.{RESET}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        if results:
            print_summary()
        sys.exit(1)
