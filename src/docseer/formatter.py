from rich.markdown import Markdown
from rich.console import Console
from rich.style import Style
from rich.prompt import Prompt
from rich.panel import Panel


class TerminalIO:
    console = Console()
    question_style = "[bold slate_blue1]"
    print_style = Style(color="sea_green2", bold=False)

    def __init__(self, is_table: bool = True,
                 width: int | None = None) -> None:
        self.input_msg = f"{self.question_style}>>> question"
        self.is_table = is_table
        self.width = width

    def ask(self) -> str:
        return Prompt.ask(self.input_msg, show_default=False)

    def answer(self, response: str) -> None:
        response = Markdown(response)
        if self.is_table:
            self.console.print(Panel(
                response, style=self.print_style,
                width=self.width, expand=self.width is None))
        else:
            self.console.print(response, style=self.print_style)


if __name__ == "__main__":
    ter = TerminalIO()
    txt = ter.ask()
    ter.answer(f'hello {txt}')
