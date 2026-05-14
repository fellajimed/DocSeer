"""
DocumentsExplorerWidget
───────────────────────
Papers management panel.  Communicates with the unified FastAPI backend via:

  GET  /papers/             – list all papers (PaperRead objects)
  POST /papers/             – add a paper from a local file path
  POST /papers/import-url   – resolve a URL via Zotero, then optionally ingest
  POST /papers/{id}/ingest  – (re-)trigger ingestion of an existing paper
  DELETE /papers/{id}       – delete paper + embeddings

The selection list shows:
  "<title or filename>  [<status>]"
The value stored per item is the paper UUID (string).
"""

from __future__ import annotations

import asyncio
import os

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Mount
from textual.widgets import (
    Button,
    ContentSwitcher,
    Input,
    Label,
    SelectionList,
    Static,
)
from textual.widgets.selection_list import Selection

from utils import AsyncRequester

API_URL = os.environ.get("DOCSEER_API_URL", "http://localhost:8000")

# Status badge colours (Rich markup)
_STATUS_STYLE: dict[str, str] = {
    "done": "bold green",
    "processing": "bold yellow",
    "pending": "yellow",
    "failed": "bold red",
    "metadata_only": "dim cyan",
}


def _paper_label(paper: dict) -> str:
    """Build a display label for a paper dict (PaperRead)."""
    raw_title = paper.get("title")
    title = raw_title.strip() if isinstance(raw_title, str) else ""
    if not title:
        title = (
            paper.get("source_path") or paper.get("url") or str(paper["id"])
        )
    # Truncate long titles
    if len(title) > 55:
        title = title[:52] + "…"
    status = paper.get("status", "")
    style = _STATUS_STYLE.get(status, "")
    badge = f"[{style}]{status}[/{style}]" if style else status
    return f"{title}  {badge}"


def _paper_name(paper: dict) -> str:
    """Return just the title / path / url of a paper (no status badge)."""
    raw_title = paper.get("title")
    name = raw_title.strip() if isinstance(raw_title, str) else ""
    if not name:
        name = paper.get("source_path") or paper.get("url") or str(paper["id"])
    if len(name) > 60:
        name = name[:57] + "…"
    return name


class DocumentsExplorerWidget(Static):
    can_focus = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # paper_id (str UUID) → paper dict
        self._papers: dict[str, dict] = {}
        # paper_id → display label (for quick search matching)
        self._labels: dict[str, str] = {}
        self._selected_ids: set[str] = set()
        # task_id -> background poller task
        self._task_watchers: dict[str, asyncio.Task[None]] = {}
        self._requester = AsyncRequester()

    # ── composition ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="main_container"):
            with Horizontal():
                with Vertical(id="selectionlist"):
                    yield Input(
                        placeholder="Search papers ...", id="search_input"
                    )
                    yield SelectionList[str](id="doc_selector")

                with Vertical(id="sidebar"):
                    yield Label(id="selected_view")

                    with Vertical(id="action_area"):
                        with ContentSwitcher(initial="launch_state"):
                            with Horizontal(id="launch_state"):
                                yield Button(
                                    "Delete Selected",
                                    variant="error",
                                    id="btn_delete",
                                )
                                yield Button(
                                    "Re-ingest",
                                    variant="primary",
                                    id="btn_reingest",
                                )
                            with Vertical(id="confirm_delete_state"):
                                yield Label(
                                    "Delete selected?", id="confirm_delete_msg"
                                )
                                with Horizontal(id="button_row_delete"):
                                    yield Button(
                                        "Yes",
                                        variant="success",
                                        id="yes_delete",
                                    )
                                    yield Button(
                                        "No!!", variant="error", id="no_delete"
                                    )
                            with Vertical(id="confirm_reingest_state"):
                                yield Label(
                                    "Re-ingest selected?",
                                    id="confirm_reingest_msg",
                                )
                                with Horizontal(id="button_row_reingest"):
                                    yield Button(
                                        "Yes",
                                        variant="success",
                                        id="yes_reingest",
                                    )
                                    yield Button(
                                        "No!!",
                                        variant="error",
                                        id="no_reingest",
                                    )

        with Horizontal(id="input_bar"):
            yield Input(
                placeholder="Path or URL to new paper ...",
                id="new_item_input",
            )
            yield Button("Add Paper", id="add_btn")

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        asyncio.create_task(self._load_papers())
        # Poll every 5 s so statuses (pending → processing → done) update
        # automatically without requiring the user to manually refresh.
        self.set_interval(5, self._load_papers)

    async def on_unmount(self) -> None:
        for watcher in self._task_watchers.values():
            watcher.cancel()
        await asyncio.gather(
            *self._task_watchers.values(), return_exceptions=True
        )
        self._task_watchers.clear()

    # ── data fetching ─────────────────────────────────────────────────────────

    async def _load_papers(self) -> None:
        try:
            response = await self._requester.request(
                method="GET",
                url=f"{API_URL}/papers/",
                stream=False,
            )
            response.raise_for_status()
            papers: list[dict] = response.json()

            self._papers = {p["id"]: p for p in papers}
            self._labels = {p["id"]: _paper_label(p) for p in papers}

            for paper in papers:
                status = paper.get("status")
                task_id = paper.get("celery_task_id")
                if status in {"pending", "processing"} and task_id:
                    self._watch_task(task_id)

            selector = self.query_one("#doc_selector", SelectionList)
            selector.clear_options()
            selector.add_options(
                [Selection(label, pid) for pid, label in self._labels.items()]
            )
            selector.border_title = f"Papers ({len(self._papers)})"

            self.query_one("#selected_view").border_title = "Selected"
            titles = [self._labels.get(pid, pid) for pid in self._selected_ids]
            self.query_one("#selected_view").update(
                "\n".join(f"• {t}" for t in titles)
            )

        except Exception as exc:
            self.notify(f"Failed to load papers: {exc}", severity="error")

    def _watch_task(self, task_id: str) -> None:
        if not task_id or task_id in self._task_watchers:
            return
        self._task_watchers[task_id] = asyncio.create_task(
            self._poll_task(task_id),
            name=f"poll-task-{task_id[:8]}",
        )

    async def _poll_task(self, task_id: str) -> None:
        try:
            while True:
                response = await self._requester.request(
                    method="GET",
                    url=f"{API_URL}/tasks/{task_id}",
                    stream=False,
                )
                data = response.json()
                state = data.get("state", "")

                if state in {"SUCCESS", "FAILURE", "REVOKED"}:
                    await self._load_papers()
                    if state == "SUCCESS":
                        paper = next(
                            (
                                p
                                for p in self._papers.values()
                                if p.get("celery_task_id") == task_id
                            ),
                            None,
                        )
                        name = (
                            _paper_name(paper) if paper else task_id[:12] + "…"
                        )
                        self.notify(f"Ingestion complete: {name}")
                    else:
                        self.notify(
                            f"Ingestion task {task_id[:12]}… ended as {state}.",
                            severity="error",
                        )
                    break

                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.notify(f"Task polling failed: {exc}", severity="error")
        finally:
            self._task_watchers.pop(task_id, None)

    # ── search ────────────────────────────────────────────────────────────────

    @on(Input.Changed, "#search_input")
    def _filter(self, event: Input.Changed) -> None:
        q = event.value.lower()
        selector = self.query_one("#doc_selector", SelectionList)
        selector.clear_options()
        selector.add_options(
            [
                Selection(label, pid, pid in self._selected_ids)
                for pid, label in self._labels.items()
                if q in label.lower()
            ]
        )

    # ── selection tracking ────────────────────────────────────────────────────

    @on(Mount)
    @on(SelectionList.SelectedChanged)
    def _update_selected(self) -> None:
        selector = self.query_one("#doc_selector", SelectionList)
        currently_shown = set(selector._values.keys())
        selected_now = set(selector.selected)

        self._selected_ids = (
            self._selected_ids - currently_shown
        ) | selected_now

        titles = [self._labels.get(pid, pid) for pid in self._selected_ids]
        self.query_one("#selected_view").update(
            "\n".join(f"• {t}" for t in titles)
        )

    # ── delete flow ───────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn_delete")
    def _show_confirm_delete(self) -> None:
        if not self._selected_ids:
            self.notify("Select at least one paper first.", severity="warning")
            return
        self.query_one(ContentSwitcher).current = "confirm_delete_state"

    @on(Button.Pressed, "#no_delete")
    def _hide_confirm_delete(self) -> None:
        self.query_one(ContentSwitcher).current = "launch_state"

    @on(Button.Pressed, "#yes_delete")
    async def _confirm_delete(self) -> None:
        ids = set(self._selected_ids)
        self.query_one(ContentSwitcher).current = "launch_state"
        self.query_one("#selected_view").update("")
        self._selected_ids.clear()

        if not ids:
            self.notify("Nothing selected!", severity="error")
            return

        tasks = [
            self._requester.request(
                method="DELETE",
                url=f"{API_URL}/papers/{pid}",
                stream=False,
            )
            for pid in ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        deleted = 0
        for pid, res in zip(ids, results):
            if isinstance(res, Exception):
                label = self._labels.get(pid, pid)
                self.notify(f"Error deleting {label}: {res}", severity="error")
            else:
                deleted += 1
                self._papers.pop(pid, None)
                self._labels.pop(pid, None)

        # Refresh list
        selector = self.query_one("#doc_selector", SelectionList)
        selector.clear_options()
        selector.add_options(
            [Selection(lbl, pid) for pid, lbl in self._labels.items()]
        )
        selector.border_title = f"Papers ({len(self._papers)})"

        if deleted:
            self.notify(f"Deleted {deleted} paper(s).")

    # ── re-ingest flow ────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn_reingest")
    def _show_confirm_reingest(self) -> None:
        if not self._selected_ids:
            self.notify("Select at least one paper first.", severity="warning")
            return
        self.query_one(ContentSwitcher).current = "confirm_reingest_state"

    @on(Button.Pressed, "#no_reingest")
    def _hide_confirm_reingest(self) -> None:
        self.query_one(ContentSwitcher).current = "launch_state"

    @on(Button.Pressed, "#yes_reingest")
    async def _confirm_reingest(self) -> None:
        ids = set(self._selected_ids)
        self.query_one(ContentSwitcher).current = "launch_state"

        for pid in ids:
            try:
                response = await self._requester.request(
                    method="POST",
                    url=f"{API_URL}/papers/{pid}/ingest",
                    stream=False,
                    json={},
                )
                response.raise_for_status()
                data = response.json()
                label = self._labels.get(pid, pid)
                task_id = data.get("task_id", "")
                if task_id:
                    self._watch_task(task_id)
                self.notify(
                    f"Re-ingesting: {label[:30]}…\nTask: {task_id[:12]}…"
                    if task_id
                    else f"Re-ingest queued: {label[:30]}…"
                )
            except Exception as exc:
                self.notify(f"Re-ingest error: {exc}", severity="error")

        await asyncio.sleep(0.5)
        await self._load_papers()

    # ── add paper ─────────────────────────────────────────────────────────────

    @on(Button.Pressed, "#add_btn")
    async def _add_paper(self) -> None:
        raw = self.query_one("#new_item_input", Input).value.strip()
        if not raw:
            return
        self.query_one("#new_item_input", Input).value = ""

        try:
            if raw.startswith("http://") or raw.startswith("https://"):
                # Resolve via Zotero Translation Server + queue ingest
                response = await self._requester.request(
                    method="POST",
                    url=f"{API_URL}/papers/import-url",
                    stream=False,
                    json={"url": raw, "trigger_ingest": True},
                )
            else:
                # Local file path — create record and queue ingest
                response = await self._requester.request(
                    method="POST",
                    url=f"{API_URL}/papers/",
                    stream=False,
                    json={"source_path": raw},
                )

            response.raise_for_status()
            data = response.json()
            task_id = data.get("task_id", "")
            if task_id:
                self._watch_task(task_id)

            self.notify(
                f"Queued for ingestion\nTask: {task_id[:12]}…"
                if task_id
                else "Added (metadata only)."
            )
            # Reload list to show the new entry
            await self._load_papers()

        except Exception as exc:
            self.notify(f"Error adding paper: {exc}", severity="error")
