import asyncio
from typing import Sequence, Optional
from langchain_core.documents import Document
from langchain_core.callbacks import Callbacks
from langchain_community.document_compressors import FlashrankRerank


class AsyncFlashrankRerank(FlashrankRerank):
    async def acompress_documents(
        self,
        documents: Sequence[Document],
        query: str,
        callbacks: Optional[Callbacks] = None,
    ) -> Sequence[Document]:
        return await asyncio.to_thread(
            self.compress_documents, documents, query, callbacks
        )
