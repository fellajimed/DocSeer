import os
import shutil
import requests
import pymupdf
from typing import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from langchain_classic.retrievers import ContextualCompressionRetriever

from .utils import get_sitemap_urls

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
    def __init__(self, source: list[str | os.PathLike[str]],
                 *, url: Iterable[str] | None = None,
                 fname: Iterable[str | os.PathLike[str]] | None = None,
                 path_db: str | os.PathLike[str] | None = None,
                 topk: int = 5, use_reranker: bool = True) -> None:
        if not (source is not None and len(source) > 0):
            raise ValueError('source should not be None or an empty list')

        self.source = source
        self.topk = topk
        self.use_reranker = use_reranker
        self.model_embeddings = OllamaEmbeddings(model="mxbai-embed-large")

        self.init_db(path_db)
        self.prepare_source()
        self.process_documents()
        self.init_retriever()

    def prepare_source(self):
        sitemap_urls = []

        for (i, source) in enumerate(self.source[:]):
            if str(source).endswith('/sitemap.xml'):
                self.source.pop(i)
                try:
                    urls = get_sitemap_urls(source)
                    sitemap_urls.extend(urls)
                except Exception:
                    print("Could not extract urls from:", source)

        if len(sitemap_urls) > 0:
            print('Found URLs in the sitemaps.')
        self.source.extend(sitemap_urls)

    def _process_document(self, index: int,
                          source: str | os.PathLike[str]) -> None:
        document = DocumentConverter().convert(source).document
        chunks = HybridChunker().chunk(document)

        ids = []
        documents = []
        title = None
        for i, chunk in enumerate(chunks):
            id = f"{index}-{i}"
            ids.append(id)
            title, doc = self._format_chunk(id, index, chunk, title)
            documents.append(doc)

        self.vector_db.add_documents(ids=ids, documents=documents)

    def _format_chunk(self, id: str, index: int,
                      chunk, title: str | None):
        heading = (chunk.meta.headings
                   if hasattr(chunk.meta, 'headings')
                   else "Unknown Heading")
        if isinstance(heading, Iterable):
            heading = ", ".join(heading)
        if title is None:
            # NOTE: heuristic -> setting the title to be the 1st heading
            title = heading

        page_numbers = ', '.join(sorted(list(set(
            str(p.page_no) for item in chunk.meta.doc_items for p in item.prov
        ))))

        metadata = {
            "title": title,
            "heading": heading,
            "filename": chunk.meta.origin.filename,
            "page_numbers": page_numbers,
            "file_index": index,
        }
        doc = Document(page_content=chunk.text, metadata=metadata, id=id)
        return title, doc

    def process_documents(self) -> None:
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
                "[cyan]Processing the documents ...",
                total=len(self.source))

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(self._process_document, i, s): i
                    for (i, s) in enumerate(self.source)
                }

                for _ in as_completed(futures):
                    # ids, documents = future.result()
                    progress.update(task_progress, advance=1)

    def add_new_document(self, url: str | None = None,
                         fname: str | os.PathLike[str] | None = None):
        if not ((url is not None) ^ (fname is not None)):
            raise ValueError('Either `url` or `fpath` should be specified:',
                             f'{url=} - {fname=}')
        _source = fname or url
        self.source.append(_source)
        self._process_document(len(self.source), _source)

    def init_retriever(self):
        base_retriever = self.vector_db.as_retriever(
            search_kwargs={"k": self.topk})

        if self.use_reranker:
            compressor = FlashrankRerank(
                client=Ranker(model_name="ms-marco-MultiBERT-L-12",
                              log_level='WARNING'),
                top_n=self.topk // 2)
            self.retriever = ContextualCompressionRetriever(
                base_compressor=compressor, base_retriever=base_retriever)
        else:
            self.retriever = base_retriever

    def invoke(self, query: str, **kwargs) -> str:
        retrieved_docs = self.retriever.invoke(query, **kwargs)

        formatted_docs = []
        for i, doc in enumerate(retrieved_docs, 1):
            metadata = doc.metadata
            title = metadata.get("title", "Unknown Title")
            file_index = metadata.get("file_index", "N/A")
            filename = metadata.get("filename", "Unknown filename")
            heading = metadata.get("heading", "Unknown Heading")
            page_numbers = metadata.get('page_numbers', 'N/A')

            formatted_docs.append(
                f"### Chunk ID {doc.id}\n"
                f" **Document Title:** {title}\n"
                f" **Document index:** {file_index}\n"
                f" **Document filename:** {filename}\n"
                f" **Heading:** {heading}\n"
                f" **Page(s): {page_numbers}\n"
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
