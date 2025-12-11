import asyncio
from typing import Any, Optional
from pydantic import Field
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever


class Retriever(BaseRetriever):
    vector_db: Any = Field(...)
    docstore: Optional[Any] = Field(None)
    topk: int = 5

    class Config:
        arbitrary_types_allowed = True

    def populate(
        self,
        chunks: list[Document],
        metadata: dict[str, str],
        parent_ids: list[Document] | None,
        parent_chunks: list[Document] | None,
    ) -> None:
        self.vector_db.add(chunks, metadata)

        if not (
            self.docstore is None
            or parent_ids is None
            and parent_chunks is None
        ):
            self.docstore.add(parent_ids, parent_chunks)

    async def apopulate(
        self,
        chunks: list[Document],
        metadata: dict[str, str],
        parent_ids: list[Document] | None,
        parent_chunks: list[Document] | None,
    ) -> None:
        await self.vector_db.aadd(chunks, metadata)

        if not (
            self.docstore is None
            or parent_ids is None
            or parent_chunks is None
        ):
            await asyncio.to_thread(
                self.docstore.add, parent_ids, parent_chunks
            )

    def retrieve(self, text: str) -> list[Document]:
        return self._get_relevant_documents(text)

    def _get_relevant_documents(self, text: str):
        chunks: list[Document] = self.vector_db.query(text, self.topk)
        if self.docstore is not None:
            # get unique parent_id
            parent_ids = list({doc.metadata["parent_id"] for doc in chunks})
            context = self.docstore.get(parent_ids)
            chunks = [
                Document(page_content=c, metadata=doc.metadata)
                for (c, doc) in zip(context, chunks)
            ]

        return chunks

    async def aretrieve(self, text: str) -> list[Document]:
        return await self._aget_relevant_documents(text)

    async def _aget_relevant_documents(self, text: str):
        chunks: list[Document] = await self.vector_db.aquery(text, self.topk)
        if self.docstore is not None:
            parent_ids = [doc.metadata["parent_id"] for doc in chunks]
            context = await asyncio.to_thread(self.docstore.get, parent_ids)
            chunks = [
                Document(page_content=c, metadata=doc.metadata)
                for (c, doc) in zip(context, chunks)
            ]

        return chunks
