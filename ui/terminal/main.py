import logging
import os
import signal
import subprocess

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, ContentSwitcher, Footer, Tab, Tabs, Label

from chatbot import ChatbotWidget
from docker_logs import DockerLogsWidget
from documents_explorer import DocumentsExplorerWidget
from settings_modal import THEME_FILE, SettingsModal
from utils import AsyncRequester

API_URL = os.environ.get("DOCSEER_API_URL", "http://localhost:8000")


class MainApp(App):
    CSS_PATH = [
        "style.tcss",
        "style_chatbot.tcss",
        "style_docs.tcss",
        "style_docker_logs.tcss",
    ]

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+s", "settings", "Settings"),
    ]
    TITLE = "DocSeer"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._requester = AsyncRequester()

    def compose(self) -> ComposeResult:
        yield Label("DocSeer", id="header-label")

        with Horizontal(id="nav_bar"):
            yield Tabs(
                Tab("Chat", id="tab_chat"),
                Tab("Papers", id="tab_files"),
                Tab("Logs", id="tab_logs"),
            )
            yield Button("■ Stop", id="btn_stop", variant="error")
            yield Button("Papers", id="btn_papers", variant="default")
            yield Button("Think: OFF", id="btn_think", variant="success")
            yield Button("Settings", id="btn_settings", variant="primary")
            yield Button("Clear Chat", id="btn_clear_chat", variant="warning")
            yield Button(
                "Clear History", id="btn_clear_history", variant="error"
            )

        with Vertical(id="main-window"):
            with ContentSwitcher(initial="tab_chat"):
                yield ChatbotWidget(id="tab_chat")
                yield DocumentsExplorerWidget(id="tab_files")
                yield DockerLogsWidget(id="tab_logs")

        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#btn_stop").display = False
        # "Papers" is only relevant on the Chat tab
        self.query_one("#btn_papers").display = True
        # Restore the last saved theme (best-effort)
        try:
            saved = THEME_FILE.read_text().strip()
            if saved and saved in self.available_themes:
                self.theme = saved
        except Exception:
            pass

    # ── paper selection sync ──────────────────────────────────────────────────

    @on(DocumentsExplorerWidget.SelectionChanged)
    def _on_papers_selection_changed(
        self, event: DocumentsExplorerWidget.SelectionChanged
    ) -> None:
        """Propagate paper-selection changes to the chat filter bar."""
        try:
            self.query_one("#tab_chat", ChatbotWidget).update_paper_display(
                event.selected
            )
        except Exception:
            pass

    # ── tab switching ─────────────────────────────────────────────────────────

    @on(Tabs.TabActivated)
    def _switch_tab(self, event: Tabs.TabActivated) -> None:
        self.query_one(ContentSwitcher).current = event.tab.id
        self.query_one("#btn_papers").display = event.tab.id == "tab_chat"
        self._set_focus()

    def _set_focus(self) -> None:
        tab_id = self.query_one(ContentSwitcher).current
        chat = self.query_one("#tab_chat", ChatbotWidget)
        if tab_id == "tab_chat":
            self.set_focus(chat.query_one("#input"))
        elif tab_id == "tab_files":
            self.set_focus(self.query_one("#doc_selector"))
        elif tab_id == "tab_logs":
            self.set_focus(self.query_one("#log-search"))
        else:
            self.set_focus(None)

    # ── papers picker ─────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn_papers")
    async def _open_papers_picker(self) -> None:
        await self.query_one("#tab_chat", ChatbotWidget)._macro_papers("")

    # ── stop generation ───────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn_stop")
    def _stop_generation(self) -> None:
        self.query_one("#tab_chat", ChatbotWidget).cancel_generation()

    @on(ChatbotWidget.GenerationStarted)
    def _on_generation_started(self) -> None:
        self.query_one("#btn_stop").display = True

    @on(ChatbotWidget.GenerationStopped)
    def _on_generation_stopped(self) -> None:
        self.query_one("#btn_stop").display = False

    # ── think mode toggle ─────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn_think")
    def _toggle_think(self, event: Button.Pressed) -> None:
        chat = self.query_one("#tab_chat", ChatbotWidget)
        new_mode = not chat.think_mode
        chat.set_think_mode(new_mode)

        if new_mode:
            event.button.label = "Think: ON"
            event.button.variant = "primary"
        else:
            event.button.label = "Think: OFF"
            event.button.variant = "success"

        self.notify(f"Thinking mode {'enabled' if new_mode else 'disabled'}.")
        self._set_focus()

    # ── settings modal ────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn_settings")
    def _open_settings(self, event: Button.Pressed) -> None:
        self.push_screen(SettingsModal(), self._on_settings_closed)

    def action_settings(self) -> None:
        self.push_screen(SettingsModal(), self._on_settings_closed)

    def _on_settings_closed(self, changes: list[str] | None) -> None:
        if changes:
            self.notify(
                "Applied: " + ", ".join(changes),
                title="Settings updated",
                severity="information",
            )
        self._set_focus()

    # ── chat controls ─────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn_clear_chat")
    def _clear_chat(self, event: Button.Pressed) -> None:
        self.query_one("#tab_chat", ChatbotWidget).clear()
        self.notify("Chat cleared (history preserved on server).")
        self._set_focus()

    @on(Button.Pressed, "#btn_clear_history")
    async def _clear_history(self, event: Button.Pressed) -> None:
        self.query_one("#tab_chat", ChatbotWidget).clear()
        try:
            await self._requester.request(
                method="DELETE",
                url=f"{API_URL}/chat/history",
                stream=False,
            )
            self.notify("Chat + server history cleared.", severity="warning")
        except Exception as exc:
            self.notify(
                f"Could not clear server history: {exc}", severity="error"
            )
        self._set_focus()

    # ── quit ──────────────────────────────────────────────────────────────────

    async def action_quit(self) -> None:
        self.notify("Stopping all services…", severity="warning")
        self.exit()


def _stop_services() -> None:
    """Stop all backend Docker containers after the TUI exits.

    Uses `docker stop` (SIGTERM → graceful shutdown) on every container in the
    SERVICES list.  The TUI container itself is intentionally excluded from that
    list, so we never try to stop ourselves.
    """
    from docker_logs import SERVICES

    containers = [s.container for s in SERVICES]
    print("\nStopping DocSeer services…", flush=True)
    try:
        subprocess.run(
            ["docker", "stop"] + containers,
            capture_output=True,
            timeout=30,
        )
        print("All services stopped.", flush=True)
    except FileNotFoundError:
        print("docker not found — services left running.", flush=True)
    except subprocess.TimeoutExpired:
        print("Timed out waiting for services to stop.", flush=True)
    except Exception as exc:
        print(f"Could not stop services: {exc}", flush=True)


if __name__ == "__main__":
    # Configure root logger at DEBUG so the DockerLogsWidget handler receives
    # all records.  No StreamHandler is added here — output goes only to the
    # RichLog widget once the app is running.
    logging.basicConfig(level=logging.DEBUG, handlers=[])

    app = MainApp()

    # Docker sends SIGTERM when the container is stopped (e.g. `docker stop`,
    # `docker compose down`).  Tell Textual to exit cleanly instead of letting
    # the process be killed mid-render.
    def _handle_sigterm(sig, frame):
        app.exit()

    signal.signal(signal.SIGTERM, _handle_sigterm)

    try:
        app.run()
    except KeyboardInterrupt:
        pass  # Ctrl+C before TUI was fully up; fall through to finally
    finally:
        _stop_services()
