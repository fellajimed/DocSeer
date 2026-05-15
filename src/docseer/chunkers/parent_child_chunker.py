import asyncio
from typing import TypedDict

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)


class ChunkResult(TypedDict):
    parent_ids: list[str]
    parent_chunks: list[Document]
    chunks: list[Document]


class ParentChildChunker:
    def __init__(
        self,
        parent_headers_to_split_on: list[tuple[str, str]] | None = None,
        child_chunk_size: int = 800,
        child_chunk_overlap: int = 80,
        parent_overlap_chars: int = 120,
    ):
        if parent_headers_to_split_on is None:
            self.parent_headers_to_split_on: list[tuple[str, str]] = [
                ("#" * i, "Header") for i in range(1, 5)
            ]
        else:
            self.parent_headers_to_split_on = parent_headers_to_split_on

        self.parent_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.parent_headers_to_split_on,
            strip_headers=False,
        )

        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=child_chunk_size,
            chunk_overlap=child_chunk_overlap,
        )
        self.parent_overlap_chars = parent_overlap_chars

    def chunk(self, document_content: str, document_id: str) -> ChunkResult:
        parent_chunks = self.parent_splitter.split_text(document_content)
        parent_ids = []
        child_chunks = []

        for i, parent_doc in enumerate(parent_chunks):
            if i > 0 and self.parent_overlap_chars > 0:
                prev = parent_chunks[i - 1].page_content
                tail = (
                    prev[-self.parent_overlap_chars :]
                    if len(prev) > self.parent_overlap_chars
                    else prev
                )
                parent_doc.page_content = tail + "\n" + parent_doc.page_content

            parent_id = f"{document_id}-{i}"
            parent_doc.id = parent_id
            parent_ids.append(parent_id)
            parent_metadata = parent_doc.metadata | {
                "parent_id": parent_id,
                "document_id": document_id,
            }

            small_chunks = self.child_splitter.split_text(
                parent_doc.page_content
            )

            for j, child_chunk in enumerate(small_chunks):
                child_doc = Document(
                    page_content=child_chunk,
                    id=f"{parent_id}-{j}",
                    metadata=parent_metadata,
                )
                child_chunks.append(child_doc)

        return dict(
            parent_ids=parent_ids,
            parent_chunks=parent_chunks,
            chunks=child_chunks,
        )

    async def achunk(
        self, document_content: str, document_id: str
    ) -> ChunkResult:
        return await asyncio.to_thread(
            self.chunk, document_content, document_id
        )
