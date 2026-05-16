"""
DocSeer CLI — run the full DocSeer stack.

Usage:
    docseer           Start services, launch TUI, then stop (default)
    docseer run       Same as above
    docseer start     Start all Docker services in background
    docseer stop      Stop all Docker services
    docseer tui       Launch TUI (assumes services already running)
    docseer ingest    Ingest one or more papers from URLs, PDF paths, or .bib files
    docseer --version Show version
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import subprocess
import sys
from functools import cache
from pathlib import Path

import httpx
import yaml


@cache
def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


@cache
def _check_docker() -> None:
    if shutil.which("docker") is None:
        print(
            "Error: docker not found. Please install Docker Desktop.",
            file=sys.stderr,
        )
        sys.exit(1)


def _load_config(path: str) -> dict[str, str]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    env: dict[str, str] = {}
    for k, v in raw.items():
        if v is None:
            continue
        val = str(v)
        if k.startswith("DOCSEER_"):
            env[k] = val
        else:
            env["DOCSEER_" + k.upper()] = val
    return env


def _merge_env(overrides: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(overrides)
    return env


def _compose(
    args: list[str], native: bool = False, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    root = _project_root()
    cmd = ["docker", "compose"]
    if native:
        cmd += [
            "-f",
            "docker-compose.yaml",
            "-f",
            "docker-compose.native-ollama.yml",
        ]
    return subprocess.run(
        cmd + args, cwd=root, env=_merge_env(env) if env else None
    )


SERVICES = [
    "postgres",
    "redis",
    "chromadb",
    "ollama",
    "grobid",
    "zotero",
    "api",
    "worker",
    "flower",
]

PORTS = """\
  API       http://localhost:8000
  Flower    http://localhost:5555
  GROBID    http://localhost:8070
  Zotero    http://localhost:1969
  PostgreSQL        5432  (Docker internal)
  Redis             6379  (Docker internal)
  ChromaDB          8000  (Docker internal)
  Ollama            11434 (Docker internal)"""


def _print_started() -> None:
    print("DocSeer is running")
    print(PORTS)
    print()


def cmd_start(args: argparse.Namespace) -> None:
    native = getattr(args, "native", False)
    _check_docker()
    cfg = _load_config(args.config) if getattr(args, "config", None) else {}
    if cfg:
        print(f"Loaded config: {args.config}")
    print("Starting DocSeer services...")
    wait = ["--wait"] if not getattr(args, "no_wait", False) else []
    up_args = ["up", "-d"] + wait
    if getattr(args, "rebuild", False):
        up_args += ["--build"]
    try:
        r = _compose(up_args + SERVICES, native=native, env=cfg or None)
        if r.returncode != 0:
            print("Failed to start services.", file=sys.stderr)
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted during startup.")
        sys.exit(1)
    _print_started()


def cmd_stop(args: argparse.Namespace) -> None:
    native = getattr(args, "native", False)
    print("Stopping DocSeer services...")
    try:
        _compose(["down"], native=native)
    except KeyboardInterrupt:
        pass
    print("DocSeer services stopped.")


def cmd_clean(args: argparse.Namespace) -> None:
    native = getattr(args, "native", False)
    print("Wiping all DocSeer volumes...")
    try:
        _compose(["down", "-v"], native=native)
    except KeyboardInterrupt:
        pass
    print("Volumes removed.")


def cmd_tui(args: argparse.Namespace) -> None:
    root = _project_root()
    sys.path.insert(0, str(root / "ui" / "terminal"))
    sys.path.insert(0, str(root / "src"))

    logging.basicConfig(level=logging.DEBUG, handlers=[])

    from main import MainApp  # ty: ignore[unresolved-import]

    app = MainApp()

    def _sigterm(s: int, f: object) -> None:
        app.exit()

    signal.signal(signal.SIGTERM, _sigterm)

    try:
        app.run()
    except KeyboardInterrupt:
        pass


def cmd_ingest(args: argparse.Namespace) -> None:
    """Ingest papers from URLs, PDF paths, or .bib files via the API."""
    api_url = os.environ.get(
        "DOCSEER_API_URL", "http://localhost:8000"
    ).rstrip("/")

    for source in args.sources:
        source = source.strip()
        if not source:
            continue

        if source.endswith(".bib"):
            _ingest_bibtex(api_url, source)
        elif source.startswith(("http://", "https://")):
            _ingest_url(api_url, source, args.trigger_ingest)
        else:
            _ingest_path(api_url, source)


def _ingest_bibtex(api_url: str, path: str) -> None:
    try:
        bibtex = Path(path).read_text(encoding="utf-8")
    except Exception as e:
        print(f"  [ERROR] reading {path}: {e}")
        return

    try:
        resp = httpx.post(
            f"{api_url}/papers/import-bibtex",
            json={"bibtex": bibtex, "trigger_ingest": True},
            timeout=120.0,
        )
        resp.raise_for_status()
        results = resp.json()
    except Exception as e:
        print(f"  [ERROR] importing {path}: {e}")
        return

    print(
        f"  BibTeX {path} — {len(results)} entr{'y' if len(results) == 1 else 'ies'}"
    )
    for r in results:
        _print_result(r)


def _ingest_url(api_url: str, url: str, trigger: bool) -> None:
    try:
        resp = httpx.post(
            f"{api_url}/papers/import-url",
            json={"url": url, "trigger_ingest": trigger},
            timeout=120.0,
        )
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        print(f"  [ERROR] {url}: {e}")
        return

    print(f"  URL {url}")
    _print_result(result)


def _ingest_path(api_url: str, path: str) -> None:
    try:
        resp = httpx.post(
            f"{api_url}/papers/",
            json={"source_path": path},
            timeout=120.0,
        )
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        print(f"  [ERROR] {path}: {e}")
        return

    print(f"  File {path}")
    _print_result(result)


def _print_result(r: dict) -> None:
    paper_id = r.get("paper_id", "?")
    status = r.get("status", "?")
    task_id = r.get("task_id", "")
    if status in ("queued", "processing"):
        print(f"    └─ id={paper_id}  status={status}  task={task_id}")
    elif status == "already_ingested":
        print(f"    └─ id={paper_id}  already ingested (task={task_id})")
    elif status == "metadata_only":
        print(f"    └─ id={paper_id}  metadata saved (no source to ingest)")
    else:
        print(f"    └─ id={paper_id}  status={status}")


def cmd_run(args: argparse.Namespace) -> None:
    native = getattr(args, "native", False)
    _check_docker()
    cfg = _load_config(args.config) if getattr(args, "config", None) else {}
    if cfg:
        print(f"Loaded config: {args.config}")
    print("Starting DocSeer services...")
    wait = ["--wait"] if not getattr(args, "no_wait", False) else []
    up_args = ["up", "-d"] + wait
    if getattr(args, "rebuild", False):
        up_args += ["--build"]
    try:
        r = _compose(up_args + SERVICES, native=native, env=cfg or None)
        if r.returncode != 0:
            print("Failed to start services.", file=sys.stderr)
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted during startup.")
        sys.exit(1)
    _print_started()
    os.environ.update(cfg)
    try:
        cmd_tui(args)
    finally:
        if not getattr(args, "keep", False):
            cmd_stop(args)


def run() -> None:
    parser = argparse.ArgumentParser(
        "docseer",
        description="DocSeer: RAG over research papers — FastAPI + Celery + ChromaDB + Ollama + Textual TUI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
Ports & services (when running):
{PORTS}
""",
    )
    parser.add_argument("--version", action="store_true", help="Show version")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser(
        "run", help="Start services, launch TUI, then stop (default)"
    )
    run_p.add_argument(
        "--keep",
        action="store_true",
        help="Keep services running after TUI exits",
    )
    run_p.add_argument(
        "--native",
        action="store_true",
        help="Use native macOS Ollama (Metal GPU)",
    )
    run_p.add_argument(
        "--no-wait", action="store_true", help="Don't wait for healthchecks"
    )
    run_p.add_argument(
        "--rebuild", action="store_true", help="Rebuild Docker images"
    )
    run_p.add_argument(
        "-c", "--config", type=str, help="Path to YAML config file"
    )

    start_p = sub.add_parser("start", help="Start all Docker services")
    start_p.add_argument(
        "--native",
        action="store_true",
        help="Use native macOS Ollama (Metal GPU)",
    )
    start_p.add_argument(
        "--no-wait", action="store_true", help="Don't wait for healthchecks"
    )
    start_p.add_argument(
        "--rebuild", action="store_true", help="Rebuild Docker images"
    )
    start_p.add_argument(
        "-c", "--config", type=str, help="Path to YAML config file"
    )

    sub.add_parser("stop", help="Stop all Docker services")
    sub.add_parser("clean", help="Stop services and wipe all volumes")
    sub.add_parser("tui", help="Launch TUI (services must already be running)")

    ingest_p = sub.add_parser(
        "ingest",
        help="Ingest papers from URLs, PDF paths, or .bib files",
    )
    ingest_p.add_argument(
        "sources",
        nargs="+",
        help="One or more sources (URL, path to PDF, path to .bib file)",
    )
    ingest_p.add_argument(
        "--no-trigger",
        dest="trigger_ingest",
        action="store_false",
        default=True,
        help="For URLs: save metadata only, skip PDF ingestion",
    )

    args = parser.parse_args()

    if args.version:
        from docseer import __version__

        print(f"DocSeer {__version__}")
        return

    if args.command == "start":
        cmd_start(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "clean":
        cmd_clean(args)
    elif args.command == "tui":
        cmd_tui(args)
    elif args.command == "ingest":
        cmd_ingest(args)
    else:
        cmd_run(args)


if __name__ == "__main__":
    run()
