"""
PaperPickerModal — TUI modal for selecting papers to filter the chat context.

Returns (via ModalScreen dismiss):
    None                         – cancelled; keep existing filter unchanged
    []                           – clear filter; chat against all papers
    [(id, title), ...]           – new filter selection
"""

from __future__ import annotations

import os
from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static
from textual.widgets import SelectionList
from textual.widgets.selection_list import Selection

from utils import AsyncRequester

API_URL = os.environ.get("DOCSEER_API_URL", "http://localhost:8000")


class PaperPickerModal(ModalScreen[list[tuple[str, str]] | None]):
    """
    Modal for picking which papers to filter the chat to.

    Parameters
    ----------
    active_ids:
        UUID strings of papers that are currently in the filter.
        These will be pre-selected when the modal opens.
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "apply", "Apply"),
    ]

    DEFAULT_CSS = """
    PaperPickerModal {
        align: center middle;
    }

    #picker-dialog {
        background: $surface;
        border: round $primary;
        padding: 1 2;
        width: 80%;
        max-width: 72;
        height: auto;
        max-height: 80%;
    }

    #picker-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $text;
    }

    #picker-search {
        margin-bottom: 1;
    }

    #picker-status {
        height: 1;
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }

    #picker-list {
        height: 12;
        border: solid $primary-darken-2;
        margin-bottom: 1;
    }

    #picker-btn-row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #picker-btn-row Button {
        margin: 0 1;
        min-width: 14;
    }
    """

    def __init__(self, active_ids: list[str] | None = None) -> None:
        super().__init__()
        self._active_ids: list[str] = list(active_ids or [])
        # Persists checked state across search re-renders (including for items
        # that are currently hidden by the search filter).
        self._pending_selection: set[str] = set(self._active_ids)
        # UUIDs of the items currently rendered in the list (in order).
        self._visible_pids: list[str] = []
        self._requester = AsyncRequester()
        # Full paper list: [(uuid_str, display_label), ...]
        self._all_papers: list[tuple[str, str]] = []

    # ── composition ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-dialog"):
            yield Static("  Filter by Papers", id="picker-title")
            yield Input(placeholder="Search papers…", id="picker-search")
            yield Static("Loading papers…", id="picker-status")
            yield SelectionList(id="picker-list")
            with Horizontal(id="picker-btn-row"):
                yield Button("Apply", id="btn-picker-apply", variant="primary")
                yield Button(
                    "Clear filter", id="btn-picker-clear", variant="warning"
                )
                yield Button(
                    "Cancel", id="btn-picker-cancel", variant="default"
                )

    def on_mount(self) -> None:
        self._load_papers()

    # ── data loading ──────────────────────────────────────────────────────────

    @work(exclusive=True)
    async def _load_papers(self) -> None:
        """Fetch ingested papers from the API and populate the list."""
        try:
            resp = await self._requester.request("GET", f"{API_URL}/papers/")
            papers = resp.json()
            self._all_papers = [
                (
                    str(p["id"]),
                    p.get("title") or p.get("source_path") or str(p["id"]),
                )
                for p in papers
                if p.get("status") == "done"
            ]
            count = len(self._all_papers)
            self.query_one("#picker-status", Static).update(
                f"{count} ingested paper{'s' if count != 1 else ''}"
            )
            self._populate_list("")
        except Exception as exc:
            self.query_one("#picker-status", Static).update(
                f"Error loading papers: {exc}"
            )
            self.notify(f"Failed to load papers: {exc}", severity="error")

    # ── list helpers ──────────────────────────────────────────────────────────

    def _sync_visible_to_pending(self) -> None:
        """Flush the current visible selections into ``_pending_selection``.

        Must be called *before* ``clear_options()`` so we capture the real
        checked state while the items are still in the list.
        """
        sel = self.query_one("#picker-list", SelectionList)
        selected_now = {str(v) for v in sel.selected}
        for pid in self._visible_pids:
            if pid in selected_now:
                self._pending_selection.add(pid)
            else:
                self._pending_selection.discard(pid)

    def _populate_list(self, query: str) -> None:
        """Re-render the SelectionList with optional substring filter.

        Selections are preserved across re-renders via ``_pending_selection``.
        We sync the visible state into ``_pending_selection`` *before* calling
        ``clear_options()`` to avoid the SelectionToggled race condition that
        fires stale deselect events during the repopulate cycle.
        """
        self._sync_visible_to_pending()
        sel = self.query_one("#picker-list", SelectionList)
        sel.clear_options()
        self._visible_pids = []
        query_lc = query.lower()
        for pid, label in self._all_papers:
            if not query_lc or query_lc in label.lower():
                self._visible_pids.append(pid)
                sel.add_option(
                    Selection(label, pid, pid in self._pending_selection)
                )

    # ── event handlers ────────────────────────────────────────────────────────

    @on(Input.Changed, "#picker-search")
    def _search_changed(self, event: Input.Changed) -> None:
        self._populate_list(event.value)

    # ── apply / cancel ────────────────────────────────────────────────────────

    def action_apply(self) -> None:
        """Dismiss with the currently selected (id, label) pairs."""
        self._sync_visible_to_pending()
        result = [
            (pid, label)
            for pid, label in self._all_papers
            if pid in self._pending_selection
        ]
        self.dismiss(result)

    def action_cancel(self) -> None:
        """Dismiss with None — caller keeps the existing filter unchanged."""
        self.dismiss(None)

    @on(Button.Pressed, "#btn-picker-apply")
    def _btn_apply(self, _: Button.Pressed) -> None:
        self.action_apply()

    @on(Button.Pressed, "#btn-picker-clear")
    def _btn_clear(self, _: Button.Pressed) -> None:
        """Dismiss with [] — caller clears the filter (chat all papers)."""
        self.dismiss([])

    @on(Button.Pressed, "#btn-picker-cancel")
    def _btn_cancel(self, _: Button.Pressed) -> None:
        self.action_cancel()
