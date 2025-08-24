import shutil
from rich.console import Console
from rich.style import Style
from rich.prompt import Prompt
from rich.table import Table


class TerminalIO:
    console = Console()
    question_style = "[bold slate_blue1]"
    print_style = Style(color="sea_green2", bold=True)

    def __init__(self, is_table: bool = True,
                 width: int | None = None) -> None:
        self.input_msg = f"{self.question_style}>>> question"
        self.is_table = is_table
        # use terminal' width if width is None
        self.width = (shutil.get_terminal_size((100, 20)).columns
                      if width is None else width)

    def ask(self) -> str:
        return Prompt.ask(self.input_msg, show_default=False)

    def answer(self, response: str) -> None:
        if self.is_table:
            table = Table(show_header=False, width=self.width)
            table.add_row(response)
            self.console.print(table, style=self.print_style)
        else:
            self.console.print(response, style=self.print_style)


if __name__ == "__main__":
    ter = TerminalIO()
    txt = ter.ask()
    ter.answer(f'hello {txt}')
