import os
import requests
import pymupdf
from pathlib import Path
from tempfile import NamedTemporaryFile
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class TextEmbedderDB:
    def __init__(self, *, url: str | None = None,
                 fname: str | os.PathLike[str] | None = None,
                 path_db: str | os.PathLike[str] | None = None,
                 topk: int = 5) -> None:
        # XOR operator
        if not ((url is not None) ^ (fname is not None)):
            raise ValueError('Either `url` or `fname` should be specified:',
                             f'{url=} - {fname=}')

        self.get_document(url, fname)
        self.chunks = HybridChunker().chunk(self._document)

        self.model_embeddeings = OllamaEmbeddings(model="mxbai-embed-large")

        self.documents = []
        self.ids = []
        for i, chunk in enumerate(self.chunks):
            id = str(i)
            self.ids.append(id)
            self.documents.append(self._format_chunk(id, chunk))

        self.init_db(path_db)
        self.topk = topk

    @property
    def retriever(self):
        return self.vector_db.as_retriever(search_kwargs={"k": self.topk})

    def invoke(self, query: str) -> str:
        formatted_docs = [
            f"--- Document from heading: {d.metadata.get('heading')} ---"
            f"\n{d.page_content}"
            for d in self.retriever.invoke(query)]
        return "\n\n".join(formatted_docs)

    def get_document(self, url: str | None,
                     fname: str | os.PathLike[str] | None) -> None:
        # save the pdf in the url to a temporary file
        if url is not None:
            response = requests.get(url)
            response.raise_for_status()

            tmp_file = NamedTemporaryFile(delete=False)
            tmp_file.write(response.content)
            tmp_file.flush()
            fname = tmp_file.name

        assert fname is not None

        converter = DocumentConverter()

        self._document = converter.convert(fname).document

        # delete the temporary file
        if url is not None:
            os.remove(fname)

    def _format_chunk(self, id: str, chunk):
        metadata = ({"heading": ", ".join(chunk.meta.headings)
                     if hasattr(chunk.meta, 'headings') else "unknown"})
        return Document(page_content=chunk.text, metadata=metadata, id=id)

    def init_db(self, path_db: str | os.PathLike[str] | None) -> None:
        default_path = (Path(__file__).resolve().absolute().parents[2]
                        / 'vector_db')

        path_db = path_db or default_path
        path_db = Path(path_db).resolve().absolute()

        if not path_db.is_file():
            path_db = default_path
        else:
            path_db.unlink(missing_ok=True)

        self.vector_db = Chroma(
            collection_name='vector_db',
            embedding_function=self.model_embeddeings,
            persist_directory=path_db,
        )

        self.vector_db.add_documents(documents=self.documents, ids=self.ids)


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
