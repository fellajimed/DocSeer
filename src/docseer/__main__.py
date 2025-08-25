import os
import sys
import shutil
import argparse

from .agent import Agent, LocalDocAgent
from .formatter import TerminalIO
from .processing import TextEmbedderDB


def answer_one_query(agent: Agent, console: TerminalIO) -> None:
    try:
        query = console.ask()
        if query == "clear":
            os.system('cls' if os.name == 'nt' else 'clear')
            return
    except (KeyboardInterrupt, EOFError):
        res = input("\nDo you really want to exit ([y]/n)? ").lower()
        if res in ("", "y", "yes"):
            console.answer("Bye Bye!")
            sys.exit()
        else:
            return
    console.answer(agent.retrieve(query))


def main() -> None:
    parser = argparse.ArgumentParser('DocSeer')
    parser.add_argument(
        '-u', '--url', type=str, nargs='*', default=[],
    )
    parser.add_argument(
        '-f', '--file-path', type=str, nargs='*', default=[],
    )
    parser.add_argument(
        '-a', '--arxiv-id', type=str, nargs='*', default=None,
    )
    parser.add_argument(
        '-k', '--top-k', type=int, default=10,
    )
    parser.add_argument(
        '-Q', '--query', type=str, default=None,
    )
    parser.add_argument(
        '-I', '--interactive', action='store_true',
    )
    args = parser.parse_args()

    if (args.query is None) and (not args.interactive):
        return

    if args.arxiv_id is not None:
        args.url += [f"https://arxiv.org/pdf/{arxiv_id}"
                     for arxiv_id in args.arxiv_id]

    try:
        console = TerminalIO(is_table=True)

        text_embedder = TextEmbedderDB(
            url=args.url, fname=args.file_path, topk=args.top_k)

        agent = LocalDocAgent(text_embedder)

        if args.interactive:
            while True:
                answer_one_query(agent, console)
        elif args.query is not None:
            console.answer(agent.retrieve(args.query))
    finally:
        # clean-ups: temporary files and database
        for (is_tmp, fpath) in getattr(text_embedder, 'files', []):
            if is_tmp and os.path.exists(fpath):
                os.remove(fpath)

        path_db = getattr(text_embedder, 'path_db', None)
        if path_db is not None:
            shutil.rmtree(path_db, ignore_errors=True)


if __name__ == "__main__":
    main()
