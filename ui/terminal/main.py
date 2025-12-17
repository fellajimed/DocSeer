import httpx
from rich.panel import Panel
from rich.align import Align
from rich.markdown import Markdown
from textual.events import Key
from textual.app import App, ComposeResult
from textual.widgets import Static, TextArea, Header, Footer
from textual.containers import VerticalScroll, Vertical

URL = "http://localhost:8000"


class SubmitTextArea(TextArea):
    """A TextArea that triggers a custom Submitted message on Ctrl+j."""

    async def _on_key(self, event: Key) -> None:
        if event.key in ("ctrl+j", "ctrl+m", "ctrl+enter"):
            event.prevent_default()
            event.stop()
            self.post_message(self.Submitted(self.text))
            self.text = ""

    class Submitted(TextArea.Changed):
        """Custom message sent when Ctrl+Enter is pressed."""

        @property
        def value(self) -> str:
            return self.text_area


class ChatMessage(Static):
    """A widget to display a single chat message bubble."""

    def __init__(self, content: str, is_user: bool, **kwargs):
        super().__init__(**kwargs)
        self.content = content
        self.is_user = is_user

    def render(self):
        console_width = self.app.console.width - 4
        if self.is_user:
            width = min(
                int(0.3 * console_width),
                max(map(len, self.content.split("\n"))) + 4,
            )
        else:
            if not self.content:
                return ""

            width = min(
                int(0.8 * console_width),
                max(map(len, self.content.split("\n"))) + 5,
            )

        panel = Panel(
            Markdown(self.content),
            style="white" if self.is_user else "magenta",
            border_style="green" if self.is_user else "magenta",
            width=width,
            padding=(0, 1),
        )

        if self.is_user:
            return Align.right(panel, width=console_width)
        else:
            return Align.left(panel, width=console_width)


class ChatApp(App):
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+q", "quit", "Quit"),
    ]
    CSS_PATH = "style.tcss"
    TITLE = "DocSeer TUI"

    def compose(self) -> ComposeResult:
        yield Header()

        with Vertical(id="chat-container"):
            with VerticalScroll(id="chat-log") as vs:
                vs.can_focus = False
            yield SubmitTextArea(
                id="input",
                placeholder="Write a query... (Ctrl+j to send)",
            )

        yield Footer()

    async def on_mount(self) -> None:
        self.chat_log = self.query_one("#chat-log", VerticalScroll)
        self.input = self.query_one("#input", SubmitTextArea)
        self.input.focus()

    async def on_submit_text_area_submitted(
        self, event: SubmitTextArea.Submitted
    ) -> None:
        user_text = event.value.strip()
        if not user_text:
            return

        user_bubble = ChatMessage(user_text, is_user=True)
        await self.chat_log.mount(user_bubble)

        user_bubble.scroll_visible()

        # self.run_worker(self.invoke_agent(user_text))
        self.run_worker(self.stream_agent(user_text))

    async def invoke_agent(self, prompt: str) -> None:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0)
            ) as client:
                response = await client.post(
                    f"{URL}/invoke", json={"query": prompt}
                )
                response_text = response.json()["response"]

            bot_bubble = ChatMessage(response_text, is_user=False)

            await self.chat_log.mount(bot_bubble)
            bot_bubble.scroll_visible()

        except Exception as e:
            error_bubble = ChatMessage(
                f"Error: {str(e)}", is_user=False, classes="bot-msg"
            )
            await self.chat_log.mount(error_bubble)

    async def stream_agent(self, prompt: str) -> None:
        bot_bubble = ChatMessage(content="", is_user=False)
        await self.chat_log.mount(bot_bubble)

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0)
            ) as client:
                async with client.stream(
                    "POST",
                    f"{URL}/stream",
                    json={"query": prompt},
                ) as response:
                    async for chunk in response.aiter_text():
                        bot_bubble.content += chunk
                        bot_bubble.scroll_visible()
        except Exception as e:
            bot_bubble.content = f"Error: {str(e)}"


if __name__ == "__main__":
    ChatApp().run()
