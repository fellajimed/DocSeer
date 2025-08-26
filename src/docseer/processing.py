import os
import shutil
import requests
import pymupdf
from typing import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.progress import (Progress, SpinnerColumn, BarColumn,
                           MofNCompleteColumn, TextColumn)
from pathlib import Path
from tempfile import NamedTemporaryFile
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from flashrank import Ranker
from langchain_community.document_compressors import FlashrankRerank
from langchain.retrievers import ContextualCompressionRetriever

import warnings
from transformers import logging

logging.set_verbosity_error()
warnings.filterwarnings("ignore")

# default value for max_workers
MAX_WORKERS = os.cpu_count() or 4


def download_url(url: str) -> str:
    try:
        response = requests.get(url)
        response.raise_for_status()
    except Exception as e:
        print(e)
        return None

    tmp_file = NamedTemporaryFile(delete=False)
    tmp_file.write(response.content)
    tmp_file.flush()
    return tmp_file.name


def download_all(urls: list[str], max_workers=MAX_WORKERS):
    results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    ) as progress:
        task_progress = progress.add_task(
            "[cyan]Downloading urls ...", total=len(urls))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(download_url, url) for url in urls]

            for future in as_completed(futures):
                if (f_path := future.result()) is not None:
                    results.append(f_path)
                progress.update(task_progress, advance=1)

    return results


class TextEmbedderDB:
    def __init__(self, *, url: Iterable[str] | None = None,
                 fname: Iterable[str | os.PathLike[str]] | None = None,
                 path_db: str | os.PathLike[str] | None = None,
                 topk: int = 5, use_reranker: bool = True) -> None:
        if not ((url is not None and len(url) > 0) or
                (fname is not None and len(fname) > 0)):
            raise ValueError('Either `url` or `fname` should be specified:',
                             f'{url=} - {fname=}')

        self.topk = topk
        self.use_reranker = use_reranker
        self.model_embeddings = OllamaEmbeddings(model="mxbai-embed-large")

        self.prepare_files(url, fname)
        self.get_documents()
        with Console().status('[cyan]Storing embeddings in the database ...',
                              spinner='dots'):
            self.init_db(path_db)

        self.init_retriever()

    def prepare_files(self, urls: list[str] | None,
                      fname: list[str | os.PathLike[str]] | None):
        self.files = []
        if fname is not None:
            is_tmp = False
            for f in fname:
                self.files.append((is_tmp, f))

        if urls is not None and len(urls) > 0:
            is_tmp = True
            for f in download_all(urls):
                self.files.append((is_tmp, f))

    def _get_document(self, index: int, is_tmp: bool,
                      fpath: str | os.PathLike[str]):
        document = DocumentConverter().convert(fpath).document
        chunks = HybridChunker().chunk(document)

        if is_tmp:
            os.remove(fpath)

        ids = []
        documents = []
        for i, chunk in enumerate(chunks):
            id = f"{index}-{i}"
            ids.append(id)
            documents.append(self._format_chunk(id, index, str(fpath), chunk))

        return ids, documents

    def _format_chunk(self, id: str, index: int, fpath: str, chunk):
        heading = (chunk.meta.headings
                   if hasattr(chunk.meta, 'headings')
                   else "Unknown Heading")
        if isinstance(heading, Iterable):
            heading = ", ".join(heading)
        metadata = {
            "heading": heading,
            "file_index": index,
            "file_name": fpath,
        }
        return Document(page_content=chunk.text, metadata=metadata, id=id)

    def get_documents(self) -> None:
        self.ids = []
        self.documents = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        ) as progress:
            task_progress = progress.add_task(
                "[cyan]Converting and chunking the documents ...",
                total=len(self.files))

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(self._get_document, i, *args): i
                    for (i, args) in enumerate(self.files)
                }

                for future in as_completed(futures):
                    ids, documents = future.result()
                    self.ids.extend(ids)
                    self.documents.extend(documents)
                    progress.update(task_progress, advance=1)

    def init_retriever(self):
        base_retriever = self.vector_db.as_retriever(
            search_kwargs={"k": self.topk})

        if self.use_reranker:
            compressor = FlashrankRerank(
                client=Ranker(model_name="ms-marco-MiniLM-L-12-v2",
                              log_level='WARNING'),
                top_n=self.topk // 2)
            self.retriever = ContextualCompressionRetriever(
                base_compressor=compressor, base_retriever=base_retriever)
        else:
            self.retriever = base_retriever

    def invoke(self, query: str) -> str:
        retrieved_docs = self.retriever.invoke(query)

        formatted_docs = []
        for i, doc in enumerate(retrieved_docs, 1):
            metadata = doc.metadata
            file_name = metadata.get("file_name", "Unknown File")
            file_index = metadata.get("file_name", "N/A")
            heading = metadata.get("heading", "Unknown Heading")

            formatted_docs.append(
                f"### Chunk ID {doc.id}\n"
                f" **File index:** {file_index}\n"
                f" **File path:** {file_name}\n"
                f" **Heading:** {heading}\n"
                f"---\n{doc.page_content}\n"
            )
        return "\n\n".join(formatted_docs)

    def init_db(self, path_db: str | os.PathLike[str] | None) -> None:
        default_path = (Path(__file__).resolve().absolute().parents[2]
                        / 'vector_db')

        path_db = path_db or default_path
        path_db = Path(path_db).resolve().absolute()

        self.path_db = path_db if path_db.exists() else default_path
        shutil.rmtree(self.path_db, ignore_errors=True)

        self.vector_db = Chroma(
            collection_name='vector_db',
            embedding_function=self.model_embeddings,
            persist_directory=self.path_db,
        )

        self.vector_db.add_documents(documents=self.documents, ids=self.ids)

        del self.documents
        del self.ids


class TextExtractor:
    def __init__(self, *, url: str | None = None,
                 fname: str | os.PathLike[str] | None = None,
                 chunk_size: int = 100, chunk_overlap: int = 100) -> None:
        # XOR operator
        if not ((url is not None) ^ (fname is not None)):
            raise ValueError('Either `url` or `fname` should be specified:',
                             f'{url=} - {fname=}')

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            length_function=len, is_separator_regex=False,
        )

        self._text = self.process(url=url, fname=fname)

    @property
    def text(self) -> str:
        return self._text

    @property
    def chunks(self) -> list[str]:
        return self.text_splitter.split_text(self._text)

    def process(self, *, url: str | None = None,
                fname: str | os.PathLike[str] | None = None) -> str:
        # save the pdf in the url to a temporary file
        if url is not None:
            response = requests.get(url)
            response.raise_for_status()

            tmp_file = NamedTemporaryFile(delete=False)
            tmp_file.write(response.content)
            tmp_file.flush()
            fname = tmp_file.name

        assert fname is not None
        text = self.extract_text(fname)

        # delete the temporary file
        if url is not None:
            os.remove(fname)

        return text

    def extract_text(self, fname: str | os.PathLike[str] | None) -> str:
        text = ""

        try:
            with pymupdf.open(fname) as doc:  # type: ignore[no-untyped-call]
                for page in doc:
                    text += page.get_text()
        except Exception as e:
            print(e)

        return text
