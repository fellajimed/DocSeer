import httpx
from rich.panel import Panel
from rich.align import Align
from rich.markdown import Markdown
from textual import on
from textual.events import Key, MouseScrollUp, MouseScrollDown
from textual.app import ComposeResult
from textual.widgets import Static, TextArea
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
            style="white",
            border_style="green" if self.is_user else "magenta",
            width=width,
            padding=(0, 1),
        )

        if self.is_user:
            return Align.right(panel, width=console_width)
        else:
            return Align.left(panel, width=console_width)


class ChatContainer(VerticalScroll):
    autoscroll = True

    @on(MouseScrollUp)
    @on(MouseScrollDown)
    def handle_mouse_scroll(self) -> None:
        if self.autoscroll:
            self.autoscroll = False


class ChatbotWidget(Static):
    def __init__(self, is_stream: bool = True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_stream = is_stream

    def compose(self) -> ComposeResult:
        with Vertical(id="chat-container"):
            with ChatContainer(id="chat-log") as vs:
                vs.can_focus = False
            yield SubmitTextArea(
                id="input",
                placeholder="Write a query... (Ctrl+j to send)",
            )

    async def on_mount(self) -> None:
        self.chat_log = self.query_one("#chat-log", ChatContainer)
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

        if self.is_stream:
            self.run_worker(self.stream_agent(user_text))
        else:
            self.run_worker(self.invoke_agent(user_text))

    async def invoke_agent(self, prompt: str) -> None:
        bot_bubble = ChatMessage(content="", is_user=False)
        bot_bubble.loading = True
        await self.chat_log.mount(bot_bubble)

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0)
            ) as client:
                response = await client.post(
                    f"{URL}/invoke", json={"query": prompt}
                )
                response_text = response.json()["response"]

            bot_bubble.loading = False
            bot_bubble.content += response_text
            bot_bubble.scroll_visible()

        except Exception as e:
            bot_bubble.content = f"Error: {str(e)}"
            bot_bubble.loading = False

    async def stream_agent(self, prompt: str) -> None:
        bot_bubble = ChatMessage(content="", is_user=False)
        bot_bubble.loading = True
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
                        if bot_bubble.loading:
                            bot_bubble.loading = False
                        bot_bubble.content += chunk
                        bot_bubble.scroll_visible()

        except Exception as e:
            bot_bubble.content = f"Error: {str(e)}"
            bot_bubble.loading = False
