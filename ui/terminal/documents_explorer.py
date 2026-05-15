"""
DocumentsExplorerWidget
───────────────────────
Papers management panel.  Communicates with the unified FastAPI backend via:

  GET  /papers/                – list all papers (PaperRead objects)
  POST /papers/                – add a paper from a local file path
  POST /papers/import-url      – resolve a URL via Zotero, then optionally ingest
  POST /papers/import-bibtex   – import metadata from a .bib file (selected entries)
  POST /papers/{id}/ingest     – (re-)trigger ingestion of an existing paper
  DELETE /papers/{id}          – delete paper + embeddings

The selection list shows:
  "<title or filename>  [<status>]"
The value stored per item is the paper UUID (string).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import bibtexparser
from bibtexparser.model import Entry

from textual import on
from textual.app import ComposeResult
from textual.message import Message
from textual.containers import Horizontal, Vertical
from textual.events import Mount
from textual.widgets import (
    Button,
    Input,
    Label,
    SelectionList,
    Static,
)
from textual.widgets.selection_list import Selection

from utils import AsyncRequester
from bibtex_import_modal import BibtexImportModal
from confirmation_modal import ConfirmationModal

API_URL = os.environ.get("DOCSEER_API_URL", "http://localhost:8000")


_STATUS_STYLE: dict[str, str] = {
    "done": "bold green",
    "processing": "bold yellow",
    "pending": "yellow",
    "failed": "bold red",
    "metadata_only": "dim cyan",
}


def _paper_label(paper: dict) -> str:
    raw_title = paper.get("title")
    title = raw_title.strip() if isinstance(raw_title, str) else ""
    if not title:
        title = (
            paper.get("source_path") or paper.get("url") or str(paper["id"])
        )
    status = paper.get("status", "")
    style = _STATUS_STYLE.get(status, "")
    badge = f"[{style}]{status}[/{style}]" if style else status
    return f"{title}  {badge}"


def _paper_name(paper: dict) -> str:
    raw_title = paper.get("title")
    name = raw_title.strip() if isinstance(raw_title, str) else ""
    if not name:
        name = paper.get("source_path") or paper.get("url") or str(paper["id"])
    return name


class DocumentsExplorerWidget(Static):
    can_focus = True

    class SelectionChanged(Message):
        """Posted when the user's paper selection changes.

        ``selected`` is a list of ``(uuid_str, display_title)`` pairs.
        An empty list means "no selection → query all papers".
        """

        def __init__(self, selected: list[tuple[str, str]]) -> None:
            super().__init__()
            self.selected = selected

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._papers: dict[str, dict] = {}
        self._labels: dict[str, str] = {}
        self._selected_ids: set[str] = set()
        self._task_watchers: dict[str, asyncio.Task[None]] = {}
        self._requester = AsyncRequester()
        self._pending_bib_entries: list[Entry] = []

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
                        with Horizontal():
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

        with Horizontal(id="input_bar"):
            yield Input(
                placeholder="Path (.pdf / .bib) or URL to new paper …",
                id="new_item_input",
            )
            yield Button("Add Paper", id="add_btn", variant="success")

    async def on_mount(self) -> None:
        asyncio.create_task(self._load_papers())
        self.set_interval(5, self._load_papers)

    async def on_unmount(self) -> None:
        for watcher in self._task_watchers.values():
            watcher.cancel()
        await asyncio.gather(
            *self._task_watchers.values(), return_exceptions=True
        )
        self._task_watchers.clear()

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
                [
                    Selection(label, pid, pid in self._selected_ids)
                    for pid, label in self._labels.items()
                ]
            )
            selector.border_title = f"Papers ({len(self._papers)})"

            self.query_one("#selected_view").border_title = "Selected"
            self._refresh_selected_view()

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

    @on(Mount)
    def _init_selected_view(self) -> None:
        """Set the sidebar title on mount (data arrives later via _load_papers)."""
        try:
            self.query_one("#selected_view").border_title = "Selected"
        except Exception:
            pass

    @on(SelectionList.SelectedChanged)
    def _update_selected(self) -> None:
        selector = self.query_one("#doc_selector", SelectionList)
        currently_shown = set(selector._values.keys())
        selected_now = set(selector.selected)
        new_selected = (self._selected_ids - currently_shown) | selected_now

        if new_selected == self._selected_ids:
            return

        self._selected_ids = new_selected
        self._refresh_selected_view()
        self._emit_selection_changed()

    def _refresh_selected_view(self) -> None:
        titles = [self._labels.get(pid, pid) for pid in self._selected_ids]
        self.query_one("#selected_view", Label).update(
            "\n".join(f"• {t}" for t in titles)
        )

    def _emit_selection_changed(self) -> None:
        selected = [
            (pid, self._labels.get(pid, pid))
            for pid in self._selected_ids
            if pid in self._labels
        ]
        self.post_message(self.SelectionChanged(selected))

    def set_selection(self, paper_ids: set[str]) -> None:
        """Programmatically update the selection (e.g. from the chat filter).

        Rebuilds the SelectionList with the new state, updates the sidebar,
        and emits ``SelectionChanged`` once.  The ``_update_selected`` guard
        suppresses the duplicate events fired by ``clear_options``/``add_options``.
        """
        self._selected_ids = set(paper_ids)
        selector = self.query_one("#doc_selector", SelectionList)
        selector.clear_options()
        selector.add_options(
            [
                Selection(label, pid, pid in self._selected_ids)
                for pid, label in self._labels.items()
            ]
        )
        self._refresh_selected_view()
        self._emit_selection_changed()

    @on(Button.Pressed, "#btn_delete")
    def _delete_selected(self) -> None:
        if not self._selected_ids:
            self.notify("Select at least one paper first.", severity="warning")
            return
        self.app.push_screen(
            ConfirmationModal("Delete selected papers?"),
            self._on_delete_confirmed,
        )

    def _on_delete_confirmed(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        ids = set(self._selected_ids)
        self.query_one("#selected_view", Label).update("")
        self._selected_ids.clear()

        if not ids:
            self.notify("Nothing selected!", severity="error")
            return

        asyncio.create_task(self._do_delete(ids))

    async def _do_delete(self, ids: set[str]) -> None:
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

        selector = self.query_one("#doc_selector", SelectionList)
        selector.clear_options()
        selector.add_options(
            [Selection(lbl, pid) for pid, lbl in self._labels.items()]
        )
        selector.border_title = f"Papers ({len(self._papers)})"

        if deleted:
            self.notify(f"Deleted {deleted} paper(s).")

    @on(Button.Pressed, "#btn_reingest")
    def _reingest_selected(self) -> None:
        if not self._selected_ids:
            self.notify("Select at least one paper first.", severity="warning")
            return
        self.app.push_screen(
            ConfirmationModal("Re-ingest selected papers?"),
            self._on_reingest_confirmed,
        )

    def _on_reingest_confirmed(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        asyncio.create_task(self._do_reingest(set(self._selected_ids)))

    async def _do_reingest(self, ids: set[str]) -> None:
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

    @on(Button.Pressed, "#add_btn")
    async def _add_paper(self) -> None:
        raw = self.query_one("#new_item_input", Input).value.strip()
        if not raw:
            return
        self.query_one("#new_item_input", Input).value = ""

        try:
            if raw.startswith("http://") or raw.startswith("https://"):
                response = await self._requester.request(
                    method="POST",
                    url=f"{API_URL}/papers/import-url",
                    stream=False,
                    json={"url": raw, "trigger_ingest": True},
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
                await self._load_papers()

            elif raw.lower().endswith(".bib"):
                bib_path = Path(raw).expanduser()
                if not bib_path.exists():
                    self.notify(
                        f"File not found: {bib_path}", severity="error"
                    )
                    return
                bib_text = bib_path.read_text(encoding="utf-8")
                library = bibtexparser.parse_string(bib_text)
                if not library.entries:
                    self.notify(
                        "No entries found in BibTeX file.", severity="warning"
                    )
                    return
                self._pending_bib_entries = list(library.entries)
                await self.app.push_screen(
                    BibtexImportModal(library.entries),
                    self._on_bibtex_import_result,
                )

            else:
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
                await self._load_papers()

        except Exception as exc:
            self.notify(f"Error adding paper: {exc}", severity="error")

    async def _on_bibtex_import_result(
        self, selected: list[Entry] | None
    ) -> None:
        """Callback after the user confirms the BibTeX selection modal.

        Selected entries are queued for ingestion (trigger_ingest=True).
        Deselected entries are saved as metadata-only records (no ingestion).
        Cancelled (None) → nothing is imported.
        """
        if selected is None:
            return

        selected_keys = {e.key for e in selected}
        not_selected = [
            e for e in self._pending_bib_entries if e.key not in selected_keys
        ]
        self._pending_bib_entries = []

        ingested = 0
        metadata = 0

        try:
            if selected:
                lib = bibtexparser.Library()
                for e in selected:
                    lib.add(e)
                resp = await self._requester.request(
                    method="POST",
                    url=f"{API_URL}/papers/import-bibtex",
                    stream=False,
                    json={
                        "bibtex": bibtexparser.write_string(lib),
                        "trigger_ingest": True,
                    },
                )
                resp.raise_for_status()
                results = resp.json()
                ingested = len(results)
                for r in results:
                    if r.get("task_id"):
                        self._watch_task(r["task_id"])

            if not_selected:
                lib2 = bibtexparser.Library()
                for e in not_selected:
                    lib2.add(e)
                resp2 = await self._requester.request(
                    method="POST",
                    url=f"{API_URL}/papers/import-bibtex",
                    stream=False,
                    json={
                        "bibtex": bibtexparser.write_string(lib2),
                        "trigger_ingest": False,
                    },
                )
                resp2.raise_for_status()
                metadata = len(resp2.json())

            total_sent = len(selected) + len(not_selected)
            skipped = total_sent - ingested - metadata
            parts = []
            if ingested:
                parts.append(f"{ingested} queued for ingestion")
            if metadata:
                parts.append(f"{metadata} saved as metadata")
            if skipped:
                parts.append(f"{skipped} already existed")
            self.notify(", ".join(parts) if parts else "Nothing new imported.")
            await self._load_papers()

        except Exception as exc:
            self.notify(f"BibTeX import error: {exc}", severity="error")
