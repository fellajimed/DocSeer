"""
ConfirmationModal — small popup asking Yes/No.

Returns (via ModalScreen dismiss):
    True   – user confirmed
    False  – user cancelled
"""

from __future__ import annotations

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmationModal(ModalScreen[bool]):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ConfirmationModal {
        align: center middle;
    }

    #confirm-dialog {
        background: $surface;
        border: round $primary;
        padding: 1 2;
        width: auto;
        max-width: 96;
        height: auto;
    }

    #confirm-msg {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $text;
        padding: 1 2;
    }

    #confirm-btn-row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #confirm-btn-row Button {
        margin: 0 4;
        min-width: 10;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(self._message, id="confirm-msg")
            with Horizontal(id="confirm-btn-row"):
                yield Button("Yes", id="btn-confirm-yes", variant="success")
                yield Button("No", id="btn-confirm-no", variant="error")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#btn-confirm-yes")
    def _btn_yes(self, _: Button.Pressed) -> None:
        self.action_confirm()

    @on(Button.Pressed, "#btn-confirm-no")
    def _btn_no(self, _: Button.Pressed) -> None:
        self.action_cancel()
