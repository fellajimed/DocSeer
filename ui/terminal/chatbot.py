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
from importlib.resources import files
from typing import Callable, Optional

from rich.align import Align
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.message import Message
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Key, MouseScrollDown, MouseScrollUp
from textual.widgets import (
    Button,
    Collapsible,
    LoadingIndicator,
    Static,
    TextArea,
)
from textual.worker import Worker

from utils import AsyncRequester

API_URL = os.environ.get("DOCSEER_API_URL", "http://localhost:8000")


MACROS: dict[str, str] = {
    "papers": "Filter chat to specific documents",
    "summarize": "Summarize selected papers",
    "extract": "Extract contributions from selected papers",
    "synthesize": "Synthesize insights across selected papers",
    "compare": "Compare selected papers side by side",
    "critique": "Critically analyze selected papers",
}


class SubmitTextArea(TextArea):
    """TextArea that submits on Ctrl+j / Ctrl+m / Ctrl+Enter.

    When the content matches a known /macro_name command, submitting posts
    MacroTriggered instead of the usual Submitted.
    """

    class MacroTriggered(Message):
        def __init__(self, name: str, args: str = "") -> None:
            super().__init__()
            self.name = name
            self.args = args

    class Submitted(TextArea.Changed):
        @property
        def value(self) -> str:
            return self.text_area

    is_worker_finished: Optional[Callable[[], bool]] = None

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if type(event) is not TextArea.Changed:
            return

        text = self.text.strip()
        if text.startswith("/"):
            self.add_class("-macro-mode")
            if len(text) > 1:
                self.text = ""
                self.remove_class("-macro-mode")
                self._macro_index = 0
                self.post_message(self.MacroTriggered("__select__", text[1:]))
        else:
            self.remove_class("-macro-mode")
            self._macro_index = 0

    async def _on_key(self, event: Key) -> None:
        if event.key == "tab":
            text = self.text.strip()
            if text.startswith("/"):
                parts = text[1:].split(None, 1)
                partial = parts[0].lower() if parts else ""
                matches = [n for n in MACROS if n.startswith(partial)]
                if len(matches) == 1:
                    macro_args = parts[1] if len(parts) > 1 else ""
                    suffix = " " if macro_args else ""
                    self.text = f"/{matches[0]}{suffix}{macro_args}"
                    cursor = len(self.text)
                    self.cursor_location = (self.cursor_location[0], cursor)
                    event.prevent_default()
                    event.stop()
                    return
            return

        text_stripped = self.text.strip()
        if text_stripped.startswith("/"):
            if event.key == "enter":
                event.prevent_default()
                event.stop()
                text = text_stripped
                self.text = ""
                self.remove_class("-macro-mode")
                parts = text[1:].split(None, 1)
                macro_name = parts[0].lower() if parts else ""
                if macro_name in MACROS:
                    if (
                        self.is_worker_finished
                        and not self.is_worker_finished()
                    ):
                        self.notify(
                            "A macro is already running.", severity="warning"
                        )
                        return
                    macro_args = parts[1] if len(parts) > 1 else ""
                    self.post_message(
                        self.MacroTriggered(macro_name, macro_args)
                    )
                    return
                self.post_message(self.Submitted(text))
                return

        if event.key not in ("ctrl+j", "ctrl+m", "ctrl+enter"):
            return

        if self.is_worker_finished and not self.is_worker_finished():
            event.prevent_default()
            event.stop()
            return

        text = self.text.strip()
        event.prevent_default()
        event.stop()

        if text.startswith("/"):
            parts = text[1:].split(None, 1)
            macro_name = parts[0].lower() if parts else ""
            macro_args = parts[1] if len(parts) > 1 else ""
            if macro_name in MACROS:
                self.text = ""
                self.post_message(self.MacroTriggered(macro_name, macro_args))
                return

        self.post_message(self.Submitted(self.text))
        self.text = ""


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

    def append_thinking(self, text: str) -> None:
        """Buffer a thinking token chunk; flush every 30 ms."""
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
        if (
            not self._thinking
            and not self._thinking_buffer
            and not self._response
        ):
            self.query_one("#bot-loading").display = False

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
        response_widget.update(Markdown(self._response))

    def mark_done(self, cancelled: bool = False) -> None:
        """Called when the SSE stream ends; ensure final state is correct."""
        if self._thinking_buffer:
            self._thinking += self._thinking_buffer
            self._thinking_buffer = ""
            content_widget = self.query_one("#thinking-content", Static)
            content_widget.update(Markdown(self._thinking))

        if self._thinking or self._thinking_done:
            self._update_collapsible_title(done=True)

        self.query_one("#bot-loading").display = False
        response_widget = self.query_one("#response-content", Static)
        response_widget.display = True

        if self._response:
            response_widget.update(Markdown(self._response))
        elif cancelled:
            response_widget.update(Text("Generation stopped.", style="dim"))
        else:
            response_widget.update("_(no response)_")
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


class ChatContainer(VerticalScroll):
    autoscroll = True

    @on(MouseScrollUp)
    def _on_scroll_up(self) -> None:
        """Freeze autoscroll the moment the user scrolls up."""
        self.autoscroll = False

    @on(MouseScrollDown)
    def _on_scroll_down(self) -> None:
        """Re-enable autoscroll when the user scrolls back to the bottom."""
        if self.max_scroll_y - self.scroll_y <= 3:
            self.autoscroll = True


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
        self._pending_macro: tuple[str, str] | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="chat-container"):
            with ChatContainer(id="chat-log") as vs:
                vs.can_focus = False
        with Horizontal(id="filter-bar"):
            yield Static("", id="filter-chips")
            yield Button("✕ Clear", id="btn-clear-filter", variant="warning")
        yield SubmitTextArea(
            id="input",
            placeholder="Ask a question… (/summarize, /extract, /synthesize, /papers)",
        )

    async def on_mount(self) -> None:
        self._chat_log = self.query_one("#chat-log", ChatContainer)
        self._input = self.query_one("#input", SubmitTextArea)
        self._input.is_worker_finished = lambda: (
            self.agent_worker is None or self.agent_worker.is_finished
        )
        self.query_one("#filter-bar").display = False
        self._input.focus()

    async def on_submit_text_area_submitted(
        self, event: SubmitTextArea.Submitted
    ) -> None:
        if self._is_macro_running():
            return
        user_text = event.value.strip()
        if not user_text:
            return
        await self._submit_query(user_text)

    def _is_macro_running(self) -> bool:
        return (
            self.agent_worker is not None and not self.agent_worker.is_finished
        )

    @on(SubmitTextArea.MacroTriggered)
    async def _on_macro_triggered(
        self, event: SubmitTextArea.MacroTriggered
    ) -> None:
        if self._is_macro_running():
            self.notify(
                "A macro is already running. Wait for it to finish.",
                severity="warning",
            )
            return
        if event.name == "papers":
            await self._macro_papers(event.args)
        elif event.name in (
            "summarize",
            "extract",
            "synthesize",
            "compare",
            "critique",
        ):
            self._pending_macro = (event.name, event.args)
            await self._macro_papers(event.args)
        elif event.name == "__select__":
            from macro_selector import MacroSelectorModal

            self.app.push_screen(
                MacroSelectorModal(event.args),
                self._on_macro_selector_result,
            )
        else:
            self.notify(f"Unknown macro: /{event.name}", severity="warning")

    def _on_macro_selector_result(self, macro_name: str | None) -> None:
        if macro_name is None:
            return
        if self._is_macro_running():
            self.notify(
                "A macro is already running. Wait for it to finish.",
                severity="warning",
            )
            return

        self._pending_macro = (macro_name, "")

        self._pending_macro = (macro_name, "")
        from documents_explorer import DocumentsExplorerWidget
        from paper_picker import PaperPickerModal

        try:
            docs = self.app.query_one(DocumentsExplorerWidget)
            active_ids = list(docs._selected_ids)
        except Exception:
            active_ids = []
        self.app.push_screen(
            PaperPickerModal(active_ids),
            self._on_paper_filter_result,
        )

    async def _macro_switch_model(self, model_name: str) -> None:
        try:
            resp = await self._requester.request(
                method="POST",
                url=f"{API_URL}/settings/models",
                stream=False,
                json={"llm_model": model_name},
            )
            resp.raise_for_status()
            changes = resp.json()
            self.notify(
                ", ".join(changes)
                if changes
                else f"Model {model_name} already active."
            )
        except Exception as exc:
            self.notify(f"Failed to switch model: {exc}", severity="error")

    async def _macro_switch_embedder(self, model_name: str) -> None:
        self.notify(
            "Changing embedding model. This may cause incompatibility with existing vectors.",
            severity="warning",
        )
        try:
            resp = await self._requester.request(
                method="POST",
                url=f"{API_URL}/settings/models",
                stream=False,
                json={"embedding_model": model_name},
            )
            resp.raise_for_status()
            changes = resp.json()
            self.notify(
                ", ".join(changes)
                if changes
                else f"Embedder {model_name} already active."
            )
        except Exception as exc:
            self.notify(f"Failed to switch embedder: {exc}", severity="error")

    def _on_macro_selector_result(self, macro_name: str | None) -> None:
        if macro_name is None:
            return
        self._pending_macro = (macro_name, "")
        from documents_explorer import DocumentsExplorerWidget
        from paper_picker import PaperPickerModal

        try:
            docs = self.app.query_one(DocumentsExplorerWidget)
            active_ids = list(docs._selected_ids)
        except Exception:
            active_ids = []
        self.app.push_screen(
            PaperPickerModal(active_ids),
            self._on_paper_filter_result,
        )

    def _macro_papers(self, args: str) -> None:
        from documents_explorer import DocumentsExplorerWidget
        from paper_picker import PaperPickerModal

        try:
            docs = self.app.query_one(DocumentsExplorerWidget)
            active_ids = list(docs._selected_ids)
        except Exception:
            active_ids = []
        self.app.push_screen(
            PaperPickerModal(active_ids), self._on_paper_filter_result
        )

    def _on_paper_filter_result(
        self, result: list[tuple[str, str]] | None
    ) -> None:
        if result is None:
            self._pending_macro = None
            return

        from documents_explorer import DocumentsExplorerWidget

        pending = self._pending_macro
        if pending:
            self._pending_macro = None
            action, args = pending
            self._run_macro_sequence(action, args, result)
            return

        try:
            docs = self.app.query_one(DocumentsExplorerWidget)
            docs.set_selection({pid for pid, _ in result})
        except Exception:
            pass

    def _run_macro_sequence(
        self, action: str, args: str, papers: list[tuple[str, str]]
    ) -> None:
        self.post_message(self.GenerationStarted())
        self.agent_worker = self.run_worker(
            self._stream_macro_sequence(action, args, papers)
        )

    async def _stream_macro_sequence(
        self, action: str, args: str, papers: list[tuple[str, str]]
    ) -> None:
        prompts_dir = files("docseer.prompts")
        prompt_file = prompts_dir / f"{action}.md"
        try:
            base_prompt = prompt_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            self.notify(
                f"Prompt template not found: {prompt_file}", severity="error"
            )
            self.post_message(self.GenerationStopped())
            return

        if args:
            base_prompt += f"\n\nFocus on: {args}"

        name = f"/{action}"

        from documents_explorer import DocumentsExplorerWidget, _paper_name

        try:
            docs = self.app.query_one(DocumentsExplorerWidget)
            paper_titles = [
                _paper_name(docs._papers.get(pid, {})) or pid[:8]
                for pid, _ in papers
            ]
        except Exception:
            paper_titles = [pid[:8] for pid, _ in papers]

        n = len(papers)
        titles_str = "\n".join(f"  {t}" for t in paper_titles)
        label = f"{name} — {n} paper{'s' if n != 1 else ''}\n{titles_str}"
        self._user_bubble = UserChatMessage(label)
        await self._chat_log.mount(self._user_bubble)
        self.call_after_refresh(self._chat_log.scroll_end)

        try:
            for pid, _ in papers:
                try:
                    docs = self.app.query_one(DocumentsExplorerWidget)
                    docs.set_selection({pid})
                    paper = docs._papers.get(pid, {})
                    title = _paper_name(paper)
                    authors_raw = paper.get("authors") or []
                    if isinstance(authors_raw, list):
                        authors = ", ".join(authors_raw)
                    else:
                        authors = str(authors_raw)
                except Exception:
                    title = pid[:8]
                    authors = ""

                meta_header = (
                    f"Title: {title}\nAuthors: {authors}\n\n" if title else ""
                )
                query = meta_header + base_prompt

                self._bot_bubble = BotChatMessage()
                self._response_buffer = ""
                self._flush_task = None
                await self._chat_log.mount(self._bot_bubble)
                self._chat_log.autoscroll = True

                paper_ids = [pid]
                try:
                    async with await self._requester.request(
                        method="POST",
                        url=f"{API_URL}/chat/stream",
                        stream=True,
                        json={
                            "query": query,
                            "think_mode": self.think_mode,
                            "paper_ids": paper_ids,
                            "topk": 100,
                        },
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
                                if (
                                    self._flush_task is None
                                    or self._flush_task.done()
                                ):
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
                                self.call_after_refresh(
                                    self._chat_log.scroll_end
                                )
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

    def update_paper_display(self, selected: list[tuple[str, str]]) -> None:
        """Update the filter bar chips to reflect the current paper selection.

        Called by MainApp whenever DocumentsExplorerWidget.SelectionChanged fires.
        ``selected`` is [(uuid_str, display_title), ...]; empty = all papers.
        """
        bar = self.query_one("#filter-bar")
        chips = self.query_one("#filter-chips", Static)
        if selected:
            labels = "  ".join(f"[{title}]" for _, title in selected)
            chips.update(labels)
            bar.display = True
        else:
            chips.update("")
            bar.display = False

    @on(Button.Pressed, "#btn-clear-filter")
    def _clear_filter(self, _: Button.Pressed) -> None:
        """Clear the selection in DocumentsExplorerWidget (→ query all papers)."""
        from documents_explorer import DocumentsExplorerWidget

        try:
            docs = self.app.query_one(DocumentsExplorerWidget)
            docs.set_selection(set())
        except Exception:
            pass
        self._input.focus()

    async def _submit_query(self, user_text: str) -> None:
        self._user_bubble = UserChatMessage(user_text)
        await self._chat_log.mount(self._user_bubble, after=self._bot_bubble)
        self.call_after_refresh(self._chat_log.scroll_end)
        self.post_message(self.GenerationStarted())
        self.agent_worker = self.run_worker(self._stream(user_text))

    async def _submit_analysis(self, label: str, prompt: str) -> None:
        self._user_bubble = UserChatMessage(label)
        await self._chat_log.mount(self._user_bubble, after=self._bot_bubble)
        self.call_after_refresh(self._chat_log.scroll_end)
        self.post_message(self.GenerationStarted())
        self.agent_worker = self.run_worker(self._stream(prompt))

    def cancel_generation(self) -> None:
        """Cancel the active streaming worker (called from MainApp's Stop button)."""
        if self.agent_worker and not self.agent_worker.is_finished:
            self.agent_worker.cancel()

    async def _stream(self, prompt: str) -> None:
        self._bot_bubble = BotChatMessage()
        self._response_buffer = ""
        self._flush_task = None
        await self._chat_log.mount(self._bot_bubble, after=self._user_bubble)

        self._chat_log.autoscroll = True
        self.call_after_refresh(self._chat_log.scroll_end)

        paper_ids: list[str] | None = None
        try:
            from documents_explorer import DocumentsExplorerWidget

            docs = self.app.query_one(DocumentsExplorerWidget)
            if docs._selected_ids:
                paper_ids = list(docs._selected_ids)
        except Exception:
            pass

        try:
            async with await self._requester.request(
                method="POST",
                url=f"{API_URL}/chat/stream",
                stream=True,
                json={
                    "query": prompt,
                    "think_mode": self.think_mode,
                    "paper_ids": paper_ids,
                },
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

    def set_think_mode(self, enabled: bool) -> None:
        self.think_mode = enabled

    def clear(self) -> None:
        self._chat_log.remove_children()
        self._user_bubble = None
        self._bot_bubble = None
