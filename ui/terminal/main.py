import asyncio
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Header,
    Footer,
    Tabs,
    Tab,
    Button,
    ContentSwitcher,
)

from chatbot import ChatbotWidget, URL
from documents_explorer import DocumentsExplorerWidget
from honcho_servers import HonchoLogWidget
from utils import AsyncRequester

RETRIEVER_URL = "http://localhost:8003"


class MainApp(App):
    CSS_PATH = [
        "style.tcss",
        "style_chatbot.tcss",
        "style_docs.tcss",
        "style_honcho_logs.tcss",
    ]

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+q", "quit", "Quit"),
    ]
    TITLE = "DocSeer TUI"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._async_requester = AsyncRequester()

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="nav_bar"):
            yield Tabs(
                Tab("Chat", id="tab_chat"),
                Tab("Papers", id="tab_files"),
                Tab("Logs", id="tab_logs"),
            )
            yield Button(
                "Thinking Mode Disabled", id="btn_think", variant="success"
            )
            yield Button(
                "Clear Chat History", id="btn_clear_chat", variant="warning"
            )
            yield Button(
                "Clear Agent History", id="btn_clear_agent", variant="error"
            )

        with Vertical(id="main-window"):
            with ContentSwitcher(initial="tab_chat"):
                yield ChatbotWidget(id="tab_chat")
                yield DocumentsExplorerWidget(id="tab_files")
                yield HonchoLogWidget(id="tab_logs")

        yield Footer()

    @on(Tabs.TabActivated)
    def handle_tab_switch(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id
        self.query_one(ContentSwitcher).current = tab_id
        self._set_focus()

    def _clear_chat(self) -> None:
        chat_window = self.query_one("#tab_chat", ChatbotWidget)
        chat_container = chat_window.query_one("#chat-log", VerticalScroll)
        chat_container.remove_children()
        chat_window.user_bubble = None
        chat_window.bot_bubble = None
        self._set_focus()

    def _set_focus(self):
        chat_window = self.query_one("#tab_chat", ChatbotWidget)
        tab_id = self.query_one(ContentSwitcher).current

        if tab_id == "tab_chat":
            self.set_focus(chat_window.query_one("#input"))
        elif tab_id == "tab_files":
            self.set_focus(self.query_one("#doc_selector"))
        else:
            self.set_focus(None)

    @on(Button.Pressed, "#btn_think")
    async def set_think_mode(self, event: Button.Pressed) -> None:
        async def wait_for_servers():
            try:
                response = await self._async_requester.request(
                    method="POST",
                    url=f"{RETRIEVER_URL}/update_think_mode",
                    stream=False,
                )
                response.raise_for_status()
                mode = response.json().get("think_mode")
                status = "Enabled" if mode else "Disabled"
                label = f"Thinking Mode {status}"
                event.button.variant = "primary" if mode else "success"
                event.button.label = label
                self.notify(label)
            except Exception as e:
                self.notify(f"Error: {str(e)}", severity="error")

        self._set_focus()
        asyncio.create_task(wait_for_servers())

    @on(Button.Pressed, "#btn_clear_chat")
    def clear_chat(self) -> None:
        self._clear_chat()
        self.notify("Chat history was cleared!")

    @on(Button.Pressed, "#btn_clear_agent")
    async def clear_agent(self) -> None:
        self._clear_chat()

        try:
            response = await self._async_requester.request(
                method="POST", url=f"{URL}/clean_agent_history", stream=False
            )
            response.raise_for_status()
        except Exception as e:
            self.notify(f"Error: {str(e)}", severity="error")

        self.notify("Agent history was cleared!", severity="warning")

    async def action_quit(self) -> None:
        log_window = self.query_one("#tab_logs", HonchoLogWidget)
        await log_window._shutdown_honcho()
        self.exit()


if __name__ == "__main__":
    MainApp().run()
