import os

# import shutil
import asyncio
from pathlib import Path
from itertools import batched
import chromadb
from langchain_core.documents import Document

from .. import CACHE_FOLDER


def documents_to_dict(batch: list[Document], doc_metadata: dict):
    d_batch = dict(ids=[], documents=[], metadatas=[])

    for doc in batch:
        d_batch["ids"].append(doc.id)
        d_batch["documents"].append(doc.page_content)
        d_batch["metadatas"].append(doc.metadata | doc_metadata)

    return d_batch


def chroma_results_to_documents(results) -> list[Document]:
    docs = []
    for doc, meta in zip(
        results.get("documents", [[]])[0], results.get("metadatas", [[]])[0]
    ):
        docs.append(Document(page_content=doc, metadata=meta))
    return docs


class ChromaVectorDB:
    def __init__(self, model_embeddings, batch_size, path_db):
        self.model_embeddings = model_embeddings
        self.batch_size = batch_size

        self._init_path(path_db)

        self.client = chromadb.PersistentClient(path=self.path_db)
        self.collection = self.client.get_or_create_collection(
            name="vector_db"
        )

    def _init_path(self, path_db: str | os.PathLike[str] | None):
        default_path = CACHE_FOLDER / "embeds_db"

        path_db = path_db or default_path
        path_db = Path(path_db).resolve().absolute()

        self.path_db = path_db if path_db.exists() else default_path
        # shutil.rmtree(self.path_db, ignore_errors=True)

    def add(self, chunks: list[Document], metadata: dict):
        for batch in batched(chunks, self.batch_size):
            d_batch = documents_to_dict(batch, metadata)
            embeds = self.model_embeddings.embed_documents(
                d_batch["documents"]
            )
            self.collection.add(embeddings=embeds, **d_batch)

    async def aadd(self, chunks: list[Document], metadata: dict):
        tasks = [
            self.embed_and_add(batch, metadata)
            for batch in batched(chunks, self.batch_size)
        ]
        await asyncio.gather(*tasks)

    async def embed_and_add(self, batch, metadata):
        d_batch = documents_to_dict(batch, metadata)
        embeds = await self.model_embeddings.aembed_documents(
            d_batch["documents"]
        )
        await asyncio.to_thread(
            self.collection.add, embeddings=embeds, **d_batch
        )

    def query(self, text: str, n_results: int = 5) -> list[Document]:
        embeds = self.model_embeddings.embed_documents(text)
        results = self.collection.query(
            query_embeddings=embeds, n_results=n_results
        )
        return chroma_results_to_documents(results)

    async def aquery(self, text: str, n_results: int = 5):
        embeds = await self.model_embeddings.aembed_documents(text)
        results = await asyncio.to_thread(
            self.collection.query, query_embeddings=embeds, n_results=n_results
        )
        return chroma_results_to_documents(results)
