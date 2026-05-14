"""
ChatbotWidget
─────────────
Streams responses from POST /chat/stream (Server-Sent Events).

SSE event format (JSON per `data:` line):
  {"type": "thinking", "content": "..."}   – reasoning tokens (think_mode)
  {"type": "response", "content": "..."}   – answer tokens
  {"type": "done"}                          – stream finished
  {"type": "error",   "content": "..."}    – error from the server

Thinking tokens are shown in a collapsible "Reasoning" panel rendered in a
dim, italic style above the regular response.  When the first response token
arrives the panel collapses automatically so it doesn't dominate the view.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Callable, Optional

from rich.align import Align
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.message import Message
from textual.containers import Vertical, VerticalScroll
from textual.events import Key, MouseScrollDown, MouseScrollUp
from textual.widgets import Collapsible, LoadingIndicator, Static, TextArea
from textual.worker import Worker

from utils import AsyncRequester

API_URL = os.environ.get("DOCSEER_API_URL", "http://localhost:8000")


# ── input widget ─────────────────────────────────────────────────────────────


class SubmitTextArea(TextArea):
    """TextArea that submits on Ctrl+j / Ctrl+m / Ctrl+Enter."""

    is_worker_finished: Optional[Callable[[], bool]] = None

    async def _on_key(self, event: Key) -> None:
        if event.key in ("ctrl+j", "ctrl+m", "ctrl+enter"):
            if self.is_worker_finished and not self.is_worker_finished():
                event.prevent_default()
                event.stop()
                return

            event.prevent_default()
            event.stop()
            self.post_message(self.Submitted(self.text))
            self.text = ""

    class Submitted(TextArea.Changed):
        @property
        def value(self) -> str:
            return self.text_area


# ── message bubbles ───────────────────────────────────────────────────────────


class UserChatMessage(Static):
    """Right-aligned user bubble."""

    def __init__(self, content: str, **kwargs):
        super().__init__(**kwargs)
        self.content = content

    def render(self):
        console_width = self.app.console.width - 4
        width = min(
            int(0.35 * console_width),
            max(len(line) for line in self.content.split("\n")) + 4,
        )
        panel = Panel(
            self.content,
            style="white",
            border_style="green",
            width=width,
            padding=(0, 1),
        )
        return Align.right(panel, width=console_width)


class BotChatMessage(Static):
    """
    Left-aligned bot response with an optional collapsible reasoning section.

    Sections:
      • Thinking panel  – dim italic, shows raw thinking tokens batched at
                          30 ms intervals.  Title shows live word count while
                          streaming ("Reasoning… (42 words)"), then settles
                          to "Reasoning (42 words)" when done.
                          Auto-collapses when the first response token arrives.
      • Response panel  – markdown-rendered response, also flushed every 30 ms.

    Both panels build up incrementally as tokens stream in.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._thinking = ""
        self._thinking_buffer = ""
        self._response = ""
        self._thinking_done = False
        self._flush_think_task: asyncio.Task[None] | None = None

    # ── composition ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield LoadingIndicator(id="bot-loading")
        with Collapsible(
            title="Reasoning",
            id="thinking-collapsible",
            collapsed=False,
        ):
            yield Static("", id="thinking-content")
        yield Static("", id="response-content")

    def on_mount(self) -> None:
        self.query_one("#thinking-collapsible").display = False
        self.query_one("#response-content").display = False
        self.query_one("#thinking-content").styles.text_style = "dim italic"

    # ── internal helpers ──────────────────────────────────────────────────────

    def _thinking_word_count(self) -> int:
        return len(self._thinking.split()) if self._thinking.strip() else 0

    def _update_collapsible_title(self, *, done: bool = False) -> None:
        wc = self._thinking_word_count()
        if wc == 0:
            title = "Reasoning…" if not done else "Reasoning"
        elif done:
            title = f"Reasoning ({wc} words)"
        else:
            title = f"Reasoning… ({wc} words)"
        collapsible = self.query_one("#thinking-collapsible", Collapsible)
        collapsible.title = title

    async def _flush_thinking_buffer(self) -> None:
        await asyncio.sleep(0.03)
        if not self._thinking_buffer:
            return
        chunk = self._thinking_buffer
        self._thinking_buffer = ""

        self._thinking += chunk
        content_widget = self.query_one("#thinking-content", Static)
        content_widget.update(Markdown(self._thinking))
        self._update_collapsible_title(done=False)

    # ── streaming helpers ────────────────────────────────────────────────────

    def append_thinking(self, text: str) -> None:
        """Buffer a thinking token chunk; flush every 30 ms."""
        # Hide spinner on first content
        if (
            not self._thinking
            and not self._thinking_buffer
            and not self._response
        ):
            self.query_one("#bot-loading").display = False

        collapsible = self.query_one("#thinking-collapsible", Collapsible)
        collapsible.display = True

        self._thinking_buffer += text
        if self._flush_think_task is None or self._flush_think_task.done():
            self._flush_think_task = asyncio.create_task(
                self._flush_thinking_buffer()
            )

    def append_response(self, text: str) -> None:
        """Append a response token chunk."""
        # Hide spinner on first content
        if (
            not self._thinking
            and not self._thinking_buffer
            and not self._response
        ):
            self.query_one("#bot-loading").display = False

        # Collapse the thinking panel the first time a response arrives
        if not self._thinking_done and (
            self._thinking or self._thinking_buffer
        ):
            collapsible = self.query_one("#thinking-collapsible", Collapsible)
            collapsible.collapsed = True
            self._update_collapsible_title(done=True)
            self._thinking_done = True

        self._response += text
        response_widget = self.query_one("#response-content", Static)
        response_widget.display = True
        # Re-parse Markdown on every 30 ms flush (batched in _flush_response_buffer).
        response_widget.update(Markdown(self._response))

    def mark_done(self, cancelled: bool = False) -> None:
        """Called when the SSE stream ends; ensure final state is correct."""
        # Flush any remaining thinking buffer synchronously
        if self._thinking_buffer:
            self._thinking += self._thinking_buffer
            self._thinking_buffer = ""
            content_widget = self.query_one("#thinking-content", Static)
            content_widget.update(Markdown(self._thinking))

        # Finalise collapsible title
        if self._thinking or self._thinking_done:
            self._update_collapsible_title(done=True)

        self.query_one("#bot-loading").display = False
        response_widget = self.query_one("#response-content", Static)
        response_widget.display = True

        if self._response:
            # Re-render in case the last flush left incomplete markdown syntax.
            response_widget.update(Markdown(self._response))
        elif cancelled:
            response_widget.update(Text("Generation stopped.", style="dim"))
        else:
            response_widget.update("_(no response)_")
            # If thinking arrived but no response, keep the reasoning panel
            # open so the user can at least read what the model thought.
            if self._thinking:
                collapsible = self.query_one(
                    "#thinking-collapsible", Collapsible
                )
                collapsible.collapsed = False

    def set_error(self, message: str) -> None:
        self.query_one("#bot-loading").display = False
        response_widget = self.query_one("#response-content", Static)
        response_widget.display = True
        response_widget.update(Text(f"Error: {message}", style="red"))


# ── scroll container ──────────────────────────────────────────────────────────


class ChatContainer(VerticalScroll):
    autoscroll = True

    @on(MouseScrollUp)
    def _on_scroll_up(self) -> None:
        """Freeze autoscroll the moment the user scrolls up."""
        self.autoscroll = False

    @on(MouseScrollDown)
    def _on_scroll_down(self) -> None:
        """Re-enable autoscroll when the user scrolls back to the bottom."""
        # max_scroll_y is the furthest the container can scroll.  A small
        # threshold (3 virtual pixels) absorbs sub-pixel rounding differences.
        if self.max_scroll_y - self.scroll_y <= 3:
            self.autoscroll = True


# ── main widget ───────────────────────────────────────────────────────────────


class ChatbotWidget(Static):
    class GenerationStarted(Message):
        """Posted when a streaming response begins."""

    class GenerationStopped(Message):
        """Posted when a streaming response ends (done, error, or cancelled)."""

    def __init__(self, think_mode: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.think_mode = think_mode
        self._bot_bubble: BotChatMessage | None = None
        self._user_bubble: UserChatMessage | None = None
        self.agent_worker: Worker | None = None
        self._requester = AsyncRequester()
        self._response_buffer = ""
        self._flush_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="chat-container"):
            with ChatContainer(id="chat-log") as vs:
                vs.can_focus = False
        yield SubmitTextArea(
            id="input",
            placeholder="Write a query... (Ctrl+j to send)",
        )

    async def on_mount(self) -> None:
        self._chat_log = self.query_one("#chat-log", ChatContainer)
        self._input = self.query_one("#input", SubmitTextArea)
        self._input.is_worker_finished = lambda: (
            self.agent_worker is None or self.agent_worker.is_finished
        )
        self._input.focus()

    async def on_submit_text_area_submitted(
        self, event: SubmitTextArea.Submitted
    ) -> None:
        user_text = event.value.strip()
        if not user_text:
            return
        await self._submit_query(user_text)

    async def _submit_query(self, user_text: str) -> None:
        self._user_bubble = UserChatMessage(user_text)
        await self._chat_log.mount(self._user_bubble, after=self._bot_bubble)
        self.call_after_refresh(self._chat_log.scroll_end)
        self.post_message(self.GenerationStarted())
        self.agent_worker = self.run_worker(self._stream(user_text))

    def cancel_generation(self) -> None:
        """Cancel the active streaming worker (called from MainApp's Stop button)."""
        if self.agent_worker and not self.agent_worker.is_finished:
            self.agent_worker.cancel()

    # ── streaming ─────────────────────────────────────────────────────────────

    async def _stream(self, prompt: str) -> None:
        self._bot_bubble = BotChatMessage()
        self._response_buffer = ""
        self._flush_task = None
        await self._chat_log.mount(self._bot_bubble, after=self._user_bubble)

        self._chat_log.autoscroll = True
        self.call_after_refresh(self._chat_log.scroll_end)

        try:
            async with await self._requester.request(
                method="POST",
                url=f"{API_URL}/chat/stream",
                stream=True,
                json={"query": prompt, "think_mode": self.think_mode},
            ) as response:
                async for raw_line in response.aiter_lines():
                    if not raw_line.startswith("data: "):
                        continue

                    try:
                        event = json.loads(raw_line[6:])
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")
                    content = event.get("content", "")

                    if event_type == "thinking":
                        self._bot_bubble.append_thinking(content)
                    elif event_type == "response":
                        self._response_buffer += content
                        if self._flush_task is None or self._flush_task.done():
                            self._flush_task = asyncio.create_task(
                                self._flush_response_buffer(),
                            )
                    elif event_type == "done":
                        await self._flush_pending_response()
                        self._bot_bubble.mark_done()
                        break
                    elif event_type == "error":
                        await self._flush_pending_response()
                        self._bot_bubble.set_error(content)
                        break

                    if self._chat_log.autoscroll:
                        self.call_after_refresh(self._chat_log.scroll_end)

        except asyncio.CancelledError:
            await self._flush_pending_response()
            if self._bot_bubble:
                self._bot_bubble.mark_done(cancelled=True)
            raise

        except Exception as exc:
            await self._flush_pending_response()
            if self._bot_bubble:
                self._bot_bubble.set_error(str(exc))

        finally:
            self.post_message(self.GenerationStopped())

    async def _flush_response_buffer(self) -> None:
        await asyncio.sleep(0.03)
        if not self._bot_bubble or not self._response_buffer:
            return
        chunk = self._response_buffer
        self._response_buffer = ""
        self._bot_bubble.append_response(chunk)
        if self._chat_log.autoscroll:
            self.call_after_refresh(self._chat_log.scroll_end)

    async def _flush_pending_response(self) -> None:
        if self._flush_task and not self._flush_task.done():
            await self._flush_task
        if self._bot_bubble and self._response_buffer:
            chunk = self._response_buffer
            self._response_buffer = ""
            self._bot_bubble.append_response(chunk)

    # ── public API called by MainApp ─────────────────────────────────────────

    def set_think_mode(self, enabled: bool) -> None:
        self.think_mode = enabled

    def clear(self) -> None:
        self._chat_log.remove_children()
        self._user_bubble = None
        self._bot_bubble = None
