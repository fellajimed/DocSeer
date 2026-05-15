import asyncio
from typing import Any, Optional
from pydantic import ConfigDict, Field
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)


class Retriever(BaseRetriever):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    vector_db: Any = Field(...)
    docstore: Optional[Any] = Field(None)
    topk: int = 5

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

    def delete_document(self, document_id: str):
        self.vector_db.delete(document_id)
        if self.docstore is not None and not self.docstore.is_empty:
            self.docstore.delete(document_id)

    def retrieve(self, text: str) -> list[Document]:
        return self.invoke(text)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        chunks: list[Document] = self.vector_db.query(query, self.topk)
        if self.docstore is not None and not self.docstore.is_empty:
            # get unique parent_id
            parent_ids = [
                p_id
                for p_id in {
                    doc.metadata.get("parent_id", None) for doc in chunks
                }
                if p_id is not None
            ]
            if not parent_ids:
                return chunks
            context = self.docstore.get(parent_ids)
            chunks = [
                Document(page_content=c, metadata=doc.metadata)
                for (c, doc) in zip(context, chunks)
            ]

        return chunks

    async def aretrieve(
        self,
        text: str,
        paper_ids: list[str] | None = None,
    ) -> list[Document]:
        """Async retrieval.

        When *paper_ids* is provided the call bypasses the LangChain
        ``ainvoke`` chain and hits ChromaDB directly with a ``$in`` filter,
        so only chunks belonging to those papers are considered.
        """
        if paper_ids is not None:
            return await self._fetch(text, paper_ids)
        return await self.ainvoke(text)

    async def _fetch(self, text: str, paper_ids: list[str]) -> list[Document]:
        """Direct retrieval path with paper_ids filter — bypasses LangChain."""
        chunks: list[Document] = await self.vector_db.aquery(
            text, self.topk, paper_ids=paper_ids
        )
        if self.docstore is not None and not self.docstore.is_empty:
            parent_ids = [
                p_id
                for p_id in {
                    doc.metadata.get("parent_id", None) for doc in chunks
                }
                if p_id is not None
            ]
            if parent_ids:
                context = await asyncio.to_thread(
                    self.docstore.get, parent_ids
                )
                chunks = [
                    Document(page_content=c, metadata=doc.metadata)
                    for c, doc in zip(context, chunks)
                ]
        return chunks

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: AsyncCallbackManagerForRetrieverRun,
    ) -> list[Document]:
        chunks: list[Document] = await self.vector_db.aquery(query, self.topk)
        if self.docstore is not None and not self.docstore.is_empty:
            parent_ids = [
                p_id
                for p_id in {
                    doc.metadata.get("parent_id", None) for doc in chunks
                }
                if p_id is not None
            ]
            if not parent_ids:
                return chunks
            context = await asyncio.to_thread(self.docstore.get, parent_ids)
            chunks = [
                Document(page_content=c, metadata=doc.metadata)
                for (c, doc) in zip(context, chunks)
            ]

        return chunks
