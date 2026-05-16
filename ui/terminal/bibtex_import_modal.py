"""
BibtexImportModal — TUI modal for selecting BibTeX entries to import.

Accepts a list of parsed bibtexparser Entry objects, presents them in a
SelectionList (all pre-selected), and returns the user's chosen subset.

Returns (via ModalScreen dismiss):
    None                 – cancelled; nothing is imported
    []                   – user deselected everything and confirmed
    [Entry, ...]         – the entries the user chose to import
"""

from __future__ import annotations

from typing import ClassVar, Sequence

from bibtexparser.model import Entry
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static
from textual.widgets import SelectionList
from textual.widgets.selection_list import Selection


def _entry_label(entry: Entry) -> str:
    """Build a short display label for a BibTeX entry."""
    fields = {f.key: f.value for f in entry.fields}
    title: str = str(fields.get("title") or entry.key or "").strip()
    year: str = str(fields.get("year") or "").strip()
    author_raw: str = str(fields.get("author") or "").strip()
    # Take only the first author surname
    first_author = ""
    if author_raw:
        first = author_raw.split(" and ")[0].strip()
        # "Last, First" → "Last"
        first_author = first.split(",")[0].strip()

    parts: list[str] = []
    if first_author:
        suffix = " et al." if " and " in author_raw else ""
        parts.append(f"{first_author}{suffix}")
    if year:
        parts.append(year)
    prefix = "  ·  ".join(parts)

    # Truncate title so the row fits in ~72 chars
    max_title = 50
    if len(title) > max_title:
        title = title[:max_title].rstrip() + "..."

    if prefix:
        return f"{prefix}  —  {title}"
    return title or entry.key


class BibtexImportModal(ModalScreen[list[Entry] | None]):
    """
    Modal for picking which BibTeX entries to import into DocSeer.

    Parameters
    ----------
    entries:
        Parsed bibtexparser Entry objects from the .bib file.
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "import_selected", "Import"),
    ]

    DEFAULT_CSS = """
    BibtexImportModal {
        align: center middle;
    }

    #bib-dialog {
        background: $surface;
        border: round $primary;
        padding: 1 2;
        width: 95%;
        max-width: 120;
        height: auto;
        max-height: 85%;
    }

    #bib-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $text;
    }

    #bib-search {
        margin-bottom: 1;
    }

    #bib-status {
        height: 1;
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }

    #bib-select-row {
        height: auto;
        align: left middle;
        margin-bottom: 1;
    }

    #bib-select-row Button {
        margin: 0 1 0 0;
        min-width: 16;
    }

    #bib-list {
        height: 14;
        border: solid $primary-darken-2;
        margin-bottom: 1;
    }

    #bib-btn-row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #bib-btn-row Button {
        margin: 0 1;
        min-width: 18;
    }
    """

    def __init__(self, entries: Sequence[Entry]) -> None:
        super().__init__()
        self._entries: list[Entry] = list(entries)
        # No entries selected by default
        self._pending: set[str] = set()
        # Keys of items currently rendered (in order)
        self._visible_keys: list[str] = []
        # Current search query
        self._search_text: str = ""

    # ── composition ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        n = len(self._entries)
        with Vertical(id="bib-dialog"):
            yield Static("  Import from BibTeX", id="bib-title")
            yield Input(placeholder="Search entries...", id="bib-search")
            yield Static(
                f"Found {n} entr{'y' if n == 1 else 'ies'}  —  selected = queued for ingestion, deselected = metadata only",
                id="bib-status",
            )
            with Horizontal(id="bib-select-row"):
                yield Button("Select All", id="btn-bib-all", variant="default")
                yield Button(
                    "Deselect All", id="btn-bib-none", variant="default"
                )
            yield SelectionList(id="bib-list")
            with Horizontal(id="bib-btn-row"):
                yield Button(
                    "Import Selected",
                    id="btn-bib-import",
                    variant="primary",
                )
                yield Button("Cancel", id="btn-bib-cancel", variant="default")

    def on_mount(self) -> None:
        self._populate_list("")
        self.query_one("#bib-search", Input).focus()

    # ── list helpers ──────────────────────────────────────────────────────────

    def _sync_visible_to_pending(self) -> None:
        """Capture visible selection state into ``_pending`` before a repopulate."""
        sel = self.query_one("#bib-list", SelectionList)
        selected_now = {str(v) for v in sel.selected}
        for key in self._visible_keys:
            if key in selected_now:
                self._pending.add(key)
            else:
                self._pending.discard(key)

    def _populate_list(self, query: str = "") -> None:
        # NOTE: do NOT call _sync_visible_to_pending() here — callers that need
        # to preserve the current widget state must sync before calling this.
        # Syncing inside _populate_list would overwrite _pending with stale
        # widget state (the widget hasn't been repopulated yet).
        sel = self.query_one("#bib-list", SelectionList)
        sel.clear_options()
        self._visible_keys = []
        query_lc = query.lower()
        for entry in self._entries:
            label = _entry_label(entry)
            if not query_lc or query_lc in label.lower():
                self._visible_keys.append(entry.key)
                sel.add_option(
                    Selection(
                        label,
                        entry.key,
                        entry.key in self._pending,
                    )
                )
        self._refresh_status()

    def _refresh_status(self) -> None:
        n_sel = len(self._pending)
        n_total = len(self._entries)
        self.query_one("#bib-status", Static).update(
            f"{n_sel} of {n_total} entr{'y' if n_total == 1 else 'ies'} selected"
        )

    # ── event handlers ────────────────────────────────────────────────────────

    @on(Input.Changed, "#bib-search")
    def _search_changed(self, event: Input.Changed) -> None:
        self._search_text = event.value
        self._populate_list(self._search_text)

    @on(SelectionList.SelectedChanged, "#bib-list")
    def _on_selection_changed(self, _: SelectionList.SelectedChanged) -> None:
        sel = self.query_one("#bib-list", SelectionList)
        self._pending = {str(v) for v in sel.selected}
        self._refresh_status()

    @on(Button.Pressed, "#btn-bib-all")
    def _select_all(self, _: Button.Pressed) -> None:
        self._pending = {e.key for e in self._entries}
        self._populate_list(self._search_text)

    @on(Button.Pressed, "#btn-bib-none")
    def _deselect_all(self, _: Button.Pressed) -> None:
        self._pending = set()
        self._populate_list(self._search_text)

    # ── import / cancel ───────────────────────────────────────────────────────

    def action_import_selected(self) -> None:
        self._sync_visible_to_pending()
        result = [e for e in self._entries if e.key in self._pending]
        self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#btn-bib-import")
    def _btn_import(self, _: Button.Pressed) -> None:
        self.action_import_selected()

    @on(Button.Pressed, "#btn-bib-cancel")
    def _btn_cancel(self, _: Button.Pressed) -> None:
        self.action_cancel()
