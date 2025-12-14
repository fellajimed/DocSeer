import os
import sys
import asyncio
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import CACHE_FOLDER, MODEL_EMBEDDINGS, LLM_MODEL, SMALL_LLM_MODEL

from .documents import Documents
from .converters import DocConverter
from .chunkers import DoclingChunker
from .databases import ChromaVectorDB, LocalFileStoreDB
from .retrievers import Retriever, MultiStepsRetriever
from .agents import BasicAgent
from .ui import ConsoleUI

import logging


def disable_logs():
    # set root logger
    logging.basicConfig(level=logging.ERROR)

    # explicitly adjust other loggers
    for logger_name in logging.root.manager.loggerDict:
        logging.getLogger(logger_name).setLevel(logging.ERROR)


def get_query_or_end(console) -> str | None:
    try:
        query = console.ask()
        if not query:
            return
        if query == "clear":
            os.system("cls" if os.name == "nt" else "clear")
            return
    except (KeyboardInterrupt, EOFError):
        res = input("\nDo you really want to exit ([y]/n)? ").lower()
        if res in ("", "y", "yes"):
            console.answer("Bye Bye!")
            sys.exit()
        else:
            return

    return query


def process_document(document, document_id, doc_converter, chunker, retriever):
    data = doc_converter.convert(document)
    content = data.pop("content", "")

    chunks = chunker.chunk(content, document_id)

    retriever.populate(**chunks, metadata=data)

    return document


def chabot(agent, retriever):
    console = ConsoleUI(is_table=True, status_desc="")

    while True:
        query = get_query_or_end(console)
        if query is None:
            continue

        with console.console.status("Retrieving ...", spinner="dots"):
            context = retriever.retrieve(query)

        with console:
            for chunk in agent.stream(query, context):
                console.stream(chunk)


def main(
    documents,
    doc_converter,
    chunker,
    retriever,
    agent,
    n_workers: int | None = None,
    index: bool = False,
):
    max_workers = n_workers or os.cpu_count() or 4

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                process_document,
                doc,
                doc_id,
                doc_converter,
                chunker,
                retriever,
            )
            for doc, doc_id in documents.docs_to_process
        ]

        for future in as_completed(futures):
            documents.cache_source(future.result())

    if not index:
        # disable logs for a clean UI
        disable_logs()
        chabot(agent, retriever)


async def aprocess_document(
    document, document_id, doc_converter, chunker, retriever
):
    data = await doc_converter.aconvert(document)
    content = data.pop("content", "")

    chunks = await chunker.achunk(content, document_id)

    await retriever.apopulate(**chunks, metadata=data)

    return document


async def achabot(agent, retriever):
    console = ConsoleUI(is_table=True, status_desc="")

    while True:
        query = get_query_or_end(console)
        if query is None:
            continue

        with console.console.status("Retrieving ...", spinner="dots"):
            context = await retriever.aretrieve(query)

        with console:
            async for chunk in agent.astream(query, context):
                console.stream(chunk)


async def amain(
    documents,
    doc_converter,
    chunker,
    retriever,
    agent,
    index: bool = False,
):
    tasks = [
        aprocess_document(doc, doc_id, doc_converter, chunker, retriever)
        for doc, doc_id in documents.docs_to_process
    ]
    results = await asyncio.gather(*tasks)

    for doc in results:
        documents.cache_source(doc)

    if not index:
        # disable logs for a clean UI
        disable_logs()
        await achabot(agent, retriever)


def parse_args():
    parser = argparse.ArgumentParser("DocSeer")

    parser.add_argument("-s", "--source", type=str, nargs="*", default=[])
    parser.add_argument("--n-workers", type=int, default=None)
    parser.add_argument("--keep-db", action="store_true")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--index", action="store_true")
    parser.add_argument("--show-logs", action="store_true")
    parser.add_argument("--version", action="store_true")

    return parser.parse_args()


def run():
    args = parse_args()

    if args.version:
        from . import __version__ as v

        print(f"DocSeer version: {v}")
        return

    if not (args.show_logs or args.index):
        disable_logs()

    documents = Documents(args.source)
    doc_converter = DocConverter()
    # chunker = ParentChildChunker()
    chunker = DoclingChunker(chunking_strat="hierarchical")

    vector_db = ChromaVectorDB(
        MODEL_EMBEDDINGS, 32, CACHE_FOLDER / "embeds_db"
    )
    docstore = LocalFileStoreDB(CACHE_FOLDER / "docstore_db")

    base_retriever = Retriever(vector_db=vector_db, docstore=docstore, topk=2)
    retriever = MultiStepsRetriever.init(
        base_retriever=base_retriever, llm=SMALL_LLM_MODEL
    )
    agent = BasicAgent(LLM_MODEL)

    if args.sync:
        main(
            documents,
            doc_converter,
            chunker,
            retriever,
            agent,
            args.n_workers,
            args.index,
        )
    else:
        asyncio.run(
            amain(
                documents,
                doc_converter,
                chunker,
                retriever,
                agent,
                args.index,
            )
        )


if __name__ == "__main__":
    run()
