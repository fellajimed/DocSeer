from rich.markdown import Markdown
from rich.console import Console
from rich.style import Style
from rich.prompt import Prompt
from rich.panel import Panel
from rich.live import Live


class ConsoleUI:
    console = Console()
    question_style = "[bold slate_blue1]"
    print_style = Style(color="sea_green2", bold=False)

    def __init__(self, is_table=True, width=None):
        self.input_msg = f"{self.question_style}\n>>> Query"
        self.width = width
        self.is_table = is_table

        self._buffer = ""
        self._live = None

    def ask(self) -> str:
        return Prompt.ask(self.input_msg, show_default=False)

    def answer(self, response: str) -> None:
        response = Markdown(response)
        if self.is_table:
            self.console.print(
                Panel(
                    response,
                    style=self.print_style,
                    width=self.width,
                    expand=self.width is None,
                )
            )
        else:
            self.console.print(response, style=self.print_style)

    def stream(self, chunk: str):
        self._buffer += chunk

        md = Markdown(self._buffer)

        if self.is_table:
            rendered = Panel(
                md,
                style=self.print_style,
                width=self.width,
                expand=self.width is None,
            )
        else:
            rendered = md

        self._live.update(rendered)

    def _start_stream(self):
        if self._live is None:
            self._live = Live(
                console=self.console,
                vertical_overflow="visible",
            )
            self._live.__enter__()

    def _end_stream(self):
        if self._live:
            self._live.__exit__(None, None, None)
            self._live = None
            self._buffer = ""

    def __enter__(self):
        self._start_stream()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._end_stream()
        return False
