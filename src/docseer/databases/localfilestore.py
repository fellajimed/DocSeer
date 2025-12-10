from pathlib import Path
from langchain_core.documents import Document
from langchain_classic.storage import LocalFileStore

from .. import CACHE_FOLDER


class LocalFileStoreDB:
    def __init__(self, path_db):
        self._init_path(path_db)
        self.docstore = LocalFileStore(self.path_db)

    def _init_path(self, path_db):
        default_path = CACHE_FOLDER / "docstore_db"

        path_db = path_db or default_path
        path_db = Path(path_db).resolve().absolute()

        self.path_db = path_db if path_db.exists() else default_path

    def add(self, ids: list[str], chunks: list[Document]):
        assert len(ids) == len(chunks)
        self.docstore.mset(
            list(zip(ids, (c.page_content.encode("utf-8") for c in chunks)))
        )

    # TODO: maybe rename this method
    def get(self, ids: list[str]) -> list[str]:
        return [content.decode("utf-8") for content in self.docstore.mget(ids)]
