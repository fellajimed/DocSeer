import os
import tempfile
import asyncio
from langchain_core.documents import Document

from docling import chunking
from docling.document_converter import DocumentConverter


class DoclingChunker:
    def __init__(self, chunking_strat: str = "hybrid"):
        chunking_strat = chunking_strat.lower()
        if "hybrid" in chunking_strat:
            self.chunker = chunking.HybridChunker()
        else:
            self.chunker = chunking.HierarchicalChunker()

    def chunk(
        self, document_content: str, document_id: str
    ) -> dict[str, list[Document]]:
        dl_doc = self._convert_str_to_docling_doc(document_content)

        chunks = []
        for i, chunk in enumerate(self.chunker.chunk(dl_doc=dl_doc)):
            # chunk.text
            chunk_text = self.chunker.contextualize(chunk=chunk)
            header = (
                chunk.meta.headings[-1]
                if hasattr(chunk.meta, "headings") and len(chunk.meta.headings)
                else "Unknown Heading"
            )
            chunks.append(
                Document(
                    page_content=chunk_text,
                    id=f"{document_id}-{i}",
                    metadata={"Header": header},
                )
            )

        return dict(
            parent_ids=None,
            parent_chunks=None,
            chunks=chunks,
        )

    async def achunk(
        self, document_content: str, document_id: str
    ) -> dict[str, list[Document]]:
        return await asyncio.to_thread(
            self.chunk, document_content, document_id
        )

    def _convert_str_to_docling_doc(self, content: str):
        """Placeholder for string-to-DoclingDocument conversion."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".md"
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            converter = DocumentConverter()
            result = converter.convert(source=tmp_path)
            return result.document
        finally:
            os.remove(tmp_path)
