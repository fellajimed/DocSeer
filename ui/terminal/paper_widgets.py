"""
Shared paper display helpers and widgets used across the TUI.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import ListItem, Static

_STATUS_STYLE: dict[str, str] = {
    "done": "bold green",
    "processing": "bold yellow",
    "pending": "yellow",
    "failed": "bold red",
    "metadata_only": "dim cyan",
}


def _paper_rich(paper: dict, selected: bool, show_status: bool = True) -> str:
    raw_title = paper.get("title")
    title = raw_title.strip() if isinstance(raw_title, str) else ""
    if not title:
        title = (
            paper.get("source_path") or paper.get("url") or str(paper["id"])
        )

    authors = paper.get("authors") or []
    author_str = ", ".join(authors[:2])
    if len(authors) > 2:
        author_str += " et al."

    if selected:
        box = "[bold green]\\[X][/bold green]"
    else:
        box = "\\[ ]"

    lines = [f"{box}  [bold]{title}[/bold]"]
    if author_str:
        lines.append(f"     [dim]{author_str}[/dim]")
    if show_status:
        status = paper.get("status", "")
        style = _STATUS_STYLE.get(status, "")
        badge = f"[{style}]{status}[/{style}]" if style else status
        lines.append(f"     {badge}")
    return "\n".join(lines)


class PaperListItem(ListItem):
    """A single paper entry with a checkbox spanning title, authors, status."""

    DEFAULT_CSS = """
    PaperListItem {
        height: auto;
        padding: 0 1;
        background: transparent;
    }
    PaperListItem.-highlight {
        background: $primary 10%;
    }
    PaperListItem.-selected {
        background: $primary 20%;
    }
    PaperListItem.-highlight.-selected {
        background: $primary 30%;
    }
    """

    def __init__(
        self, paper_id: str, paper: dict, show_status: bool = True, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.paper_id = paper_id
        self.paper = paper
        self.selected = False
        self.show_status = show_status

    def compose(self) -> ComposeResult:
        yield Static(
            _paper_rich(self.paper, self.selected, self.show_status),
            id=f"paper_{self.paper_id}",
        )

    def refresh_display(self) -> None:
        self.query_one(f"#paper_{self.paper_id}", Static).update(
            _paper_rich(self.paper, self.selected, self.show_status)
        )
        if self.selected:
            self.add_class("-selected")
        else:
            self.remove_class("-selected")
