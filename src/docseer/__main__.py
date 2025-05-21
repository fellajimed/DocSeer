import os
import sys
import argparse

from .agent import DocAgent
from .formatter import TerminalIO
from .utils import TextExtractor


def answer_one_query(agent: DocAgent, console: TerminalIO) -> None:
    try:
        query = console.ask()
        if query == "clear":
            os.system('cls' if os.name == 'nt' else 'clear')
            return
    except (KeyboardInterrupt, EOFError):
        res = input("\nDo you really want to exit ([y]/n)? ")
        if res in ["", "y", "yes"]:
            console.answer("Hope you had fun :) Bye Bye!")
            sys.exit()
        else:
            return
    console.answer(agent.retrieve(query))


def main() -> None:
    parser = argparse.ArgumentParser('DocSeer')
    parser.add_argument(
        '-u', '--url', type=str, default=None,
    )
    parser.add_argument(
        '-f', '--file-path', type=str, default=None,
    )
    parser.add_argument(
        '-a', '--arxiv-id', type=str, default=None,
    )
    parser.add_argument(
        '-S', '--summarize', action='store_true',
    )
    parser.add_argument(
        '-I', '--interactive', action='store_true',
    )
    args = parser.parse_args()

    if (not args.summarize) and (not args.interactive):
        return

    console = TerminalIO(is_table=True)
    text = TextExtractor(url=args.url, fname=args.file_path).text
    agent = DocAgent(text=text)

    if args.summarize:
        response = "Here is a summary of the pdf:\n"
        response += agent.summarize()
        console.answer(response)

    if args.interactive:
        while True:
            answer_one_query(agent, console)


if __name__ == "__main__":
    main()
