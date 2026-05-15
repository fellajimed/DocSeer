import asyncio
from itertools import batched

import chromadb
from langchain_core.documents import Document


def _documents_to_dict(batch: list[Document], doc_metadata: dict) -> dict:
    d_batch: dict[str, list] = dict(ids=[], documents=[], metadatas=[])
    for doc in batch:
        d_batch["ids"].append(doc.id)
        d_batch["documents"].append(doc.page_content)
        d_batch["metadatas"].append(doc.metadata | doc_metadata)
    return d_batch


def _chroma_results_to_documents(results) -> list[Document]:
    docs = []
    for doc, meta in zip(
        results.get("documents", [[]])[0],
        results.get("metadatas", [[]])[0],
    ):
        docs.append(Document(page_content=doc, metadata=meta))
    return docs


class ChromaVectorDB:
    COLLECTION_NAME = "vector_db"

    def __init__(
        self,
        model_embeddings,
        batch_size: int = 128,
        path_db=None,  # kept for backward compat, unused
        chroma_host: str = "localhost",
        chroma_port: int = 8010,
    ):
        self.model_embeddings = model_embeddings
        self.batch_size = batch_size

        self.client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME
        )

    # ------------------------------------------------------------------ sync

    def add(self, chunks: list[Document], metadata: dict) -> None:
        for batch in batched(chunks, self.batch_size):
            d_batch = _documents_to_dict(list(batch), metadata)
            embeds = self.model_embeddings.embed_documents(
                d_batch["documents"]
            )
            self.collection.add(embeddings=embeds, **d_batch)

    def delete(self, document_id: str) -> None:
        self.collection.delete(where={"document_id": document_id})

    def query(
        self,
        text: str,
        n_results: int = 5,
        paper_ids: list[str] | None = None,
    ) -> list[Document]:
        embeds = self.model_embeddings.embed_query(text)
        kwargs: dict = dict(query_embeddings=[embeds], n_results=n_results)
        if paper_ids:
            kwargs["where"] = {"document_id": {"$in": paper_ids}}
        results = self.collection.query(**kwargs)
        return _chroma_results_to_documents(results)

    # ----------------------------------------------------------------- async

    async def aadd(self, chunks: list[Document], metadata: dict) -> None:
        tasks = [
            self._embed_and_add(list(batch), metadata)
            for batch in batched(chunks, self.batch_size)
        ]
        await asyncio.gather(*tasks)

    async def _embed_and_add(
        self, batch: list[Document], metadata: dict
    ) -> None:
        d_batch = _documents_to_dict(batch, metadata)
        embeds = await self.model_embeddings.aembed_documents(
            d_batch["documents"]
        )
        await asyncio.to_thread(
            self.collection.add, embeddings=embeds, **d_batch
        )

    async def aquery(
        self,
        text: str,
        n_results: int = 5,
        paper_ids: list[str] | None = None,
    ) -> list[Document]:
        embeds = await self.model_embeddings.aembed_query(text)
        kwargs: dict = dict(query_embeddings=[embeds], n_results=n_results)
        if paper_ids:
            kwargs["where"] = {"document_id": {"$in": paper_ids}}
        results = await asyncio.to_thread(self.collection.query, **kwargs)
        return _chroma_results_to_documents(results)
