from __future__ import annotations

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, ListItem, ListView, Static

from .chatbot import MACROS as _MACROS


class MacroSelectorModal(ModalScreen[str | None]):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    MacroSelectorModal {
        align: center middle;
    }

    #macro-dialog {
        background: $surface;
        border: round $primary;
        padding: 1 2;
        width: 90%;
        max-width: 96;
        height: auto;
        max-height: 60%;
    }

    #macro-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $text;
    }

    #macro-search {
        margin-bottom: 1;
    }

    #macro-list {
        height: 10;
        border: solid $primary-darken-2;
        margin-bottom: 1;
    }

    #macro-list:focus-within {
        border: solid $accent;
    }

    #macro-hint {
        height: 1;
        color: $text-muted;
        text-style: italic;
        text-align: center;
    }
    """

    def __init__(self, query: str = "") -> None:
        super().__init__()
        self._query = query
        self._filtered_names: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="macro-dialog"):
            yield Static("  Macros", id="macro-title")
            yield Input(
                placeholder="Type to filter macros...",
                id="macro-search",
                value=self._query,
            )
            yield ListView(id="macro-list")
            yield Static(
                "↑↓ navigate  │  Enter select  │  Esc cancel", id="macro-hint"
            )

    def on_mount(self) -> None:
        self._populate_list(self._query)
        self.query_one("#macro-search", Input).focus()

    def _populate_list(self, query: str) -> None:
        query_lc = query.lower()
        self._filtered_names = [
            name
            for name, desc in _MACROS.items()
            if not query_lc or query_lc in name or query_lc in desc.lower()
        ]
        list_view = self.query_one("#macro-list", ListView)
        list_view.clear()

        for name in self._filtered_names:
            desc = _MACROS[name]
            list_view.mount(
                ListItem(
                    Static(f"/{name}  —  {desc}"),
                )
            )

    @on(Input.Changed, "#macro-search")
    def _search_changed(self, event: Input.Changed) -> None:
        self._populate_list(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(ListView.Selected)
    def _on_selected(self, event: ListView.Selected) -> None:
        index = self.query_one("#macro-list", ListView).index
        if index is not None and 0 <= index < len(self._filtered_names):
            self.dismiss(self._filtered_names[index])
