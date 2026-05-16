"""
SettingsModal — TUI modal for changing LLM, embedding model, and UI theme.

Each model picker is a FuzzyModelSelect widget: a search Input plus a live-
filtered OptionList.  Fuzzy matching ranks consecutive character hits higher
than scattered ones, so "q3" surfaces "qwen3:8b" before "qwen2.5:3b".

Keyboard flow inside each picker:
  Type            – filter the list in real time
  Down / Tab      – move focus from Input into the OptionList
  Up (at index 0) – move focus back to the Input
  Enter / click   – confirm the highlighted option, clear search

Modal bindings:
  Ctrl+S  – Apply
  Escape  – Cancel
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from utils import AsyncRequester

API_URL = os.environ.get("DOCSEER_API_URL", "http://localhost:8000")

# Persist the chosen theme across TUI restarts
THEME_FILE = Path.home() / ".docseer_theme"


# ── fuzzy scorer ──────────────────────────────────────────────────────────────


def _fuzzy_score(query: str, target: str) -> int | None:
    """
    Returns a score (lower = better) when every character in *query* appears
    in *target* in order (case-insensitive), or None when there is no match.

    Consecutive character matches receive a smaller penalty than scattered
    ones, so "q3" scores "qwen3:8b" lower (better) than "qwen2.5:32b".
    """
    if not query:
        return 0
    q, t = query.lower(), target.lower()
    qi, score, prev = 0, 0, -2
    for ti, ch in enumerate(t):
        if ch == q[qi]:
            score += 1 if ti == prev + 1 else 4
            prev = ti
            qi += 1
            if qi == len(q):
                return score
    return None


# ── FuzzyModelSelect ──────────────────────────────────────────────────────────


class FuzzyModelSelect(Widget):
    """
    Composite picker: Input (search query) + OptionList (filtered results).

    Public API:
        widget.set_models(models, current="")   – populate + pre-select
        widget.value                             – currently selected str | None
    """

    DEFAULT_CSS = """
    FuzzyModelSelect {
        height: auto;
    }
    FuzzyModelSelect Input {
        margin-bottom: 0;
    }
    FuzzyModelSelect OptionList {
        max-height: 6;
        border: solid $primary-darken-2;
    }
    """

    def __init__(
        self, placeholder: str = "Type to search...", **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._all_models: list[str] = []
        self._placeholder = placeholder
        self._selected: str | None = None
        self._suppress = (
            False  # guard against re-filtering on programmatic Input writes
        )

    @property
    def value(self) -> str | None:
        return self._selected

    # ── composition ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Input(placeholder=self._placeholder)
        yield OptionList()

    # ── public helpers ────────────────────────────────────────────────────────

    def set_models(self, models: list[str], current: str = "") -> None:
        """Populate the picker.  Pre-highlights *current* if it is in *models*."""
        self._all_models = models
        self._selected = current if current in models else None

        inp = self.query_one(Input)
        inp.placeholder = (
            f"Search... (active: {current})" if current else self._placeholder
        )
        self._refresh_list("")
        if current in models:
            self.query_one(OptionList).highlighted = models.index(current)

    # ── list management ───────────────────────────────────────────────────────

    def _refresh_list(self, query: str) -> None:
        opt = self.query_one(OptionList)
        opt.clear_options()
        if not query:
            for m in self._all_models:
                opt.add_option(Option(m))
        else:
            scored = sorted(
                (
                    (score, m)
                    for m in self._all_models
                    if (score := _fuzzy_score(query, m)) is not None
                ),
                key=lambda x: x[0],
            )
            for _, m in scored:
                opt.add_option(Option(m))

    # ── event handlers ────────────────────────────────────────────────────────

    @on(Input.Changed)
    def _input_changed(self, event: Input.Changed) -> None:
        if self._suppress:
            return
        self._refresh_list(event.value)

    @on(OptionList.OptionHighlighted)
    def _option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Track the highlighted item so Tab → Apply works without pressing Enter."""
        if event.option.prompt is not None:
            self._selected = str(event.option.prompt)

    @on(OptionList.OptionSelected)
    def _option_selected(self, event: OptionList.OptionSelected) -> None:
        """Confirm selection, fill Input, and restore the full list."""
        chosen = str(event.option.prompt)
        self._selected = chosen
        inp = self.query_one(Input)
        self._suppress = True
        inp.value = chosen
        inp.placeholder = f"Search... (active: {chosen})"
        self._suppress = False
        self._refresh_list("")
        inp.focus()

    def on_key(self, event: Key) -> None:
        """Down from Input → OptionList; Up at index 0 → Input."""
        inp = self.query_one(Input)
        opt = self.query_one(OptionList)
        if event.key == "down" and inp.has_focus and opt.option_count > 0:
            opt.focus()
            event.stop()
        elif (
            event.key == "up" and opt.has_focus and (opt.highlighted or 0) == 0
        ):
            inp.focus()
            event.stop()


# ── SettingsModal ─────────────────────────────────────────────────────────────


class SettingsModal(ModalScreen[list[str] | None]):
    """Modal dialog for hot-swapping LLM / embedding models and UI theme."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "apply", "Apply"),
    ]

    DEFAULT_CSS = """
    SettingsModal {
        align: center middle;
    }

    #settings-dialog {
        background: $surface;
        border: round $primary;
        padding: 1 2;
        width: 95%;
        max-width: 120;
        height: auto;
    }

    #settings-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $text;
    }

    .setting-row {
        height: auto;
        margin-bottom: 1;
    }

    .setting-label {
        margin-bottom: 0;
        color: $text-muted;
        text-style: italic;
    }

    .setting-divider {
        height: 1;
        margin: 1 0;
        border-top: solid $primary 20%;
    }

    #btn-row {
        height: auto;
        margin-top: 1;
        align: center middle;
    }

    #btn-apply {
        margin-right: 1;
        min-width: 10;
    }

    #btn-cancel {
        min-width: 10;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._requester = AsyncRequester(retry_timeout=3.0)
        self._llm_current: str = ""
        self._embed_current: str = ""
        self._theme_current: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("⚙  Settings", id="settings-title")

            with Vertical(classes="setting-row"):
                yield Label("LLM Model", classes="setting-label")
                yield FuzzyModelSelect(
                    placeholder="Search LLM models...",
                    id="sel-llm",
                )

            with Vertical(classes="setting-row"):
                yield Label("Embedding Model", classes="setting-label")
                yield FuzzyModelSelect(
                    placeholder="Search embedding models...",
                    id="sel-embed",
                )

            yield Static("", classes="setting-divider")

            with Vertical(classes="setting-row"):
                yield Label("Theme", classes="setting-label")
                yield FuzzyModelSelect(
                    placeholder="Search themes...",
                    id="sel-theme",
                )

            with Horizontal(id="btn-row"):
                yield Button("Apply", id="btn-apply", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="default")

    def on_mount(self) -> None:
        self._load_data()

    @work(exclusive=True)
    async def _load_data(self) -> None:
        """Fetch available models from the API and themes from the app."""
        # ── models ────────────────────────────────────────────────────────────
        try:
            models_resp = await self._requester.request(
                "GET", f"{API_URL}/models"
            )
            current_resp = await self._requester.request(
                "GET", f"{API_URL}/settings/models"
            )
            models: list[str] = models_resp.json()
            current = current_resp.json()

            self._llm_current = current.get("llm_model", "")
            self._embed_current = current.get("embedding_model", "")

            self.query_one("#sel-llm", FuzzyModelSelect).set_models(
                models, self._llm_current
            )
            self.query_one("#sel-embed", FuzzyModelSelect).set_models(
                models, self._embed_current
            )

        except Exception as exc:
            self.notify(f"Failed to load models: {exc}", severity="error")

        # ── themes ────────────────────────────────────────────────────────────
        try:
            themes = sorted(self.app.available_themes.keys())
            self._theme_current = self.app.theme
            self.query_one("#sel-theme", FuzzyModelSelect).set_models(
                themes, self._theme_current
            )
        except Exception as exc:
            self.notify(f"Failed to load themes: {exc}", severity="warning")

    # ── apply / cancel ────────────────────────────────────────────────────────

    async def _do_apply(self) -> None:
        changes: list[str] = []

        # ── model changes (via API) ───────────────────────────────────────────
        llm_val = self.query_one("#sel-llm", FuzzyModelSelect).value
        embed_val = self.query_one("#sel-embed", FuzzyModelSelect).value

        if llm_val == self._llm_current:
            llm_val = None
        if embed_val == self._embed_current:
            embed_val = None

        if llm_val is not None or embed_val is not None:
            try:
                resp = await self._requester.request(
                    "POST",
                    f"{API_URL}/settings/models",
                    json={"llm_model": llm_val, "embedding_model": embed_val},
                )
                model_changes: list[str] = resp.json()
                changes.extend(model_changes)
            except Exception as exc:
                self.notify(f"Failed to apply models: {exc}", severity="error")

        # ── theme change (local) ──────────────────────────────────────────────
        theme_val = self.query_one("#sel-theme", FuzzyModelSelect).value
        if theme_val and theme_val != self._theme_current:
            self.app.theme = theme_val
            changes.append(f"theme → {theme_val}")
            try:
                THEME_FILE.write_text(theme_val)
            except Exception:
                pass  # persistence is best-effort

        self.dismiss(changes if changes else None)

    @on(Button.Pressed, "#btn-apply")
    async def _btn_apply(self, event: Button.Pressed) -> None:
        await self._do_apply()

    async def action_apply(self) -> None:
        await self._do_apply()

    @on(Button.Pressed, "#btn-cancel")
    def _cancel(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
