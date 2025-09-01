from typing import Any
from rich.live import Live
from rich.panel import Panel
from rich.markdown import Markdown
from rich.console import Console, Group
from langchain_core.agents import AgentFinish
from langchain.callbacks.base import BaseCallbackHandler


class RichCallbackHandler(BaseCallbackHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.panels = []
        self.live = None
        self.main_panel = Panel(Group(*self.panels),
                                title="Agent Executor Log")
        self.console = Console()
        self.live = None

    def _update_live_display(self) -> None:
        """
        Helper to update the live display with the current group of panels.
        """
        if self.live is not None:
            self.main_panel.renderable = Group(*self.panels)
            self.live.refresh()

    def on_chain_start(self, serialized, inputs, **kwargs) -> None:
        if "name" in kwargs:
            name = kwargs["name"]
        elif serialized:
            name = serialized.get(
                "name", serialized.get("id", ["<unknown>"])[-1])
        else:
            name = "<unknown>"
        self.panels.append(
            Panel(Markdown(f"Entering new chain: {name}"),
                  title="Chain Started", style="bold blue")
        )

        self.main_panel.renderable = Group(*self.panels)
        self.live = Live(self.main_panel,
                         console=self.console,
                         vertical_overflow="visible",
                         # refresh_per_second=5,
                         auto_refresh=False)
        self.live.start()
        self.live.refresh()

    def on_chain_end(self, outputs: dict[str, Any], **kwargs) -> None:
        self.panels.append(
            Panel(Markdown(f"Output: {outputs}"),
                  title="Chain Finish", style="bold blue")
        )
        self._update_live_display()
        if self.live:
            self.live.stop()
        self.panels = []

    def on_chain_error(self, error, **kwargs) -> None:
        self.panels.append(
            Panel(Markdown(str(error)), title="Chain Error", style="bold red")
        )
        self._update_live_display()

    def on_tool_start(self, serialized, input_str, **kwargs) -> None:
        self.panels.append(
            Panel(Markdown(input_str),
                  title=f"Tool Started: {serialized['name']}",
                  style="bold yellow")
        )
        self._update_live_display()

    def on_tool_end(self, output, **kwargs) -> None:
        self.panels.append(
            Panel(Markdown(output), title="Tool Ended", style="bold yellow")
        )
        self._update_live_display()

    def on_agent_action(self, action, **kwargs) -> None:
        self.panels.append(
            Panel(action.log, title="Agent Action", style="bold cyan")
        )
        self._update_live_display()

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> None:
        self.panels.append(
            Panel(Markdown(finish.log), title="Agent Finished",
                  style="bold cyan")
        )
        self._update_live_display()
