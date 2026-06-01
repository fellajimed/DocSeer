"""
DockerLogsWidget
────────────────
Runs one `docker logs -f --tail=100 <container>` subprocess per service and
streams the output into a single shared RichLog widget, colour-coded by service.

Additionally installs a Python logging.Handler so that any log records emitted
by the TUI process itself (logging.getLogger(...)) also appear in the same pane,
labelled "app" in bright_cyan.  This makes application-level warnings and errors
visible in both native and Docker run modes.

Container names follow the `docseer-<service>` convention set in
docker-compose.yaml.  Lines from dead/missing containers are silently skipped
until the container appears.

Note: docseer-tui is intentionally excluded — the TUI process's own logs are
captured by _RichLogHandler above and shown under the "app" label instead.

Search
──────
A search bar at the top filters visible lines by case-insensitive substring
match (against service name + log text).  All lines are kept in an internal
buffer so that clearing the filter restores the full history.  Press Escape
to clear the search and return focus to the log.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Callable, NamedTuple

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Key
from textual.widgets import Input, RichLog, Static


class _Service(NamedTuple):
    container: str
    colour: str


SERVICES: list[_Service] = [
    _Service("docseer-api", "cyan"),
    _Service("docseer-worker", "yellow"),
    _Service("docseer-flower", "bright_yellow"),
    _Service("docseer-postgres", "blue"),
    _Service("docseer-redis", "bright_red"),
    _Service("docseer-chromadb", "green"),
    _Service("docseer-ollama", "magenta"),
    _Service("docseer-grobid", "white"),
    _Service("docseer-zotero", "bright_white"),
]

_LABEL_WIDTH = max(len(s.container) for s in SERVICES)

_MAX_LINES = 5_000


_LEVEL_COLOUR: dict[int, str] = {
    logging.DEBUG: "dim",
    logging.INFO: "white",
    logging.WARNING: "bright_yellow",
    logging.ERROR: "red",
    logging.CRITICAL: "bold red",
}

_LEVEL_BADGE: dict[int, str] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO ",
    logging.WARNING: "WARN ",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRIT ",
}

_QUIET_LOGGERS = [
    "httpx",
    "httpcore",
    "asyncio",
    "hpack",
    "urllib3",
    "charset_normalizer",
]


class _RichLogHandler(logging.Handler):
    """Routes Python log records into the DockerLogsWidget line buffer.

    Takes a *write_fn* callback — ``DockerLogsWidget._write_buffered`` — so
    that "app" log records are buffered and searchable like any other line.

    Format (per line):
        HH:MM:SS  [bright_cyan]app             [/]  [level_colour]│ BADGE  logger — message[/]
    """

    LABEL = "app"

    def __init__(self, write_fn: Callable[[str, str], None]) -> None:
        super().__init__()
        self._write_fn = write_fn

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            ts = datetime.now().strftime("%H:%M:%S")
            label = self.LABEL.ljust(_LABEL_WIDTH)
            colour = _LEVEL_COLOUR.get(record.levelno, "white")
            badge = _LEVEL_BADGE.get(record.levelno, "?    ")
            markup = (
                f"[dim]{ts} [/dim]"
                f"[bright_cyan]{label}[/bright_cyan] "
                f"[{colour}]│ {badge}  {escape(msg)}[/{colour}]"
            )
            plain = f"{self.LABEL} {badge} {msg}"
            self._write_fn(markup, plain)
        except Exception:
            self.handleError(record)


class _AutoScrollLog(RichLog):
    """RichLog that freezes autoscroll when the user scrolls up and re-enables
    it when they scroll back near the bottom — mirrors ChatContainer behaviour."""

    def on_mouse_scroll_up(self) -> None:
        self.auto_scroll = False

    def on_mouse_scroll_down(self) -> None:
        if self.max_scroll_y - self.scroll_y <= 3:
            self.auto_scroll = True


class DockerLogsWidget(Static):
    """
    A widget that tails Docker container logs and displays them colour-coded
    by service in a single scrollable Log pane.

    Also captures Python logging records from the TUI process itself and
    displays them under the "app" label in bright_cyan.

    A search bar at the top filters visible lines by case-insensitive substring
    match.  All lines are buffered so clearing the filter restores full history.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._log_buffer: list[tuple[str, str]] = []
        self._filter: str = ""

    def compose(self) -> ComposeResult:
        with Horizontal(id="log-search-bar"):
            yield Input(
                placeholder="Search logs... (Esc to clear)",
                id="log-search",
            )
        yield _AutoScrollLog(
            id="docker-log",
            highlight=False,
            markup=True,
            wrap=True,
            max_lines=_MAX_LINES,
        )

    async def on_mount(self) -> None:
        self._log = self.query_one(_AutoScrollLog)
        self._tasks: list[asyncio.Task] = []

        self._log_handler = _RichLogHandler(self._write_buffered)
        self._log_handler.setLevel(logging.DEBUG)
        self._log_handler.setFormatter(
            logging.Formatter("%(name)s — %(message)s")
        )
        root_logger = logging.getLogger()
        root_logger.addHandler(self._log_handler)
        if (
            root_logger.level == logging.NOTSET
            or root_logger.level > logging.DEBUG
        ):
            root_logger.setLevel(logging.DEBUG)
        for name in _QUIET_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)

        for service in SERVICES:
            task = asyncio.create_task(
                self._tail(service),
                name=f"tail-{service.container}",
            )
            self._tasks.append(task)

    @on(Input.Changed, "#log-search")
    def _on_search_changed(self, event: Input.Changed) -> None:
        self._filter = event.value.strip().lower()
        self._apply_filter()

    def on_key(self, event: Key) -> None:
        """Escape clears the search and returns focus to the log."""
        if event.key == "escape":
            search = self.query_one("#log-search", Input)
            if search.value:
                search.value = ""
                event.stop()
            elif search.has_focus:
                self._log.focus()
                event.stop()

    def _apply_filter(self) -> None:
        """Clear the RichLog and re-render only lines matching the current filter."""
        self._log.clear()
        q = self._filter
        for markup, plain in self._log_buffer:
            if not q or q in plain:
                self._log.write(markup)

        if not self._filter:
            self._log.auto_scroll = True
            self._log.scroll_end(animate=False)
        else:
            self._log.auto_scroll = False

    def _write_buffered(self, markup: str, plain: str) -> None:
        """Append to the line buffer and conditionally write to the RichLog."""
        self._log_buffer.append((markup, plain))
        if len(self._log_buffer) > _MAX_LINES:
            del self._log_buffer[: len(self._log_buffer) - _MAX_LINES]

        if not self._filter or self._filter in plain:
            self._log.write(markup)

    def _write(self, service: _Service, line: str) -> None:
        """Format one container log line and pass it through the buffer."""
        ts = datetime.now().strftime("%H:%M:%S")
        label = service.container.ljust(_LABEL_WIDTH)
        markup = (
            f"[dim]{ts} [/dim]"
            f"[{service.colour}]{label} │ [/{service.colour}]"
            f"{escape(line)}"
        )
        plain = f"{service.container} {line}".lower()
        self._write_buffered(markup, plain)

    def _write_system(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        label = "system".ljust(_LABEL_WIDTH)
        markup = f"[dim]{ts} {label} │ {escape(message)}[/dim]"
        plain = f"system {message}".lower()
        self._write_buffered(markup, plain)

    async def _tail(self, service: _Service) -> None:
        """
        Continuously follow logs for *service*.

        If the container doesn't exist yet, retries every 3 s so that the
        widget works even when started before the backend is fully up.
        """
        while True:
            proc: asyncio.subprocess.Process | None = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker",
                    "logs",
                    "-f",
                    "--tail=100",
                    service.container,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                assert proc.stdout is not None

                async for raw_line in proc.stdout:
                    line = raw_line.decode(errors="replace").rstrip()
                    self._write(service, line)

                await proc.wait()

            except asyncio.CancelledError:
                if proc is not None and proc.returncode is None:
                    proc.terminate()
                    with contextlib.suppress(Exception):
                        await proc.wait()
                raise

            except (FileNotFoundError, PermissionError) as exc:
                self._write_system(f"[docker] {exc}")
                await asyncio.sleep(10)
                continue

            except Exception as exc:
                self._write_system(f"[{service.container}] error: {exc}")

            await asyncio.sleep(3)

    async def on_unmount(self) -> None:
        """Called by Textual on any exit path — Ctrl+C, SIGTERM, action_quit."""
        await self.shutdown()

    async def shutdown(self) -> None:
        """Cancel all tailing tasks and remove the logging handler (idempotent)."""
        root_logger = logging.getLogger()
        if hasattr(self, "_log_handler"):
            root_logger.removeHandler(self._log_handler)

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
