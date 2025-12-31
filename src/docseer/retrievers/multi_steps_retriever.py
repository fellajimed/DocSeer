from typing import Any
from pydantic import Field, PrivateAttr
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_classic.retrievers.document_compressors import LLMChainExtractor
from .async_flashrankrerank import AsyncFlashrankRerank


class MultiStepsRetriever(BaseRetriever):
    base_retriever: BaseRetriever = Field(...)
    llm: Any = Field(None)
    reranker: AsyncFlashrankRerank | None = Field(None)
    extractor: LLMChainExtractor | None = Field(None)
    multi_query: MultiQueryRetriever | None = Field(None)
    summarizer_llm: Any = Field(None)
    max_summary_tokens: int = 2048
    _think_mode: bool = PrivateAttr(default=False)

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def init(
        cls,
        base_retriever: BaseRetriever,
        llm=None,
        reranker=None,
        use_extractor=False,
        summarizer_llm=None,
        max_summary_tokens=2048,
        think_mode=False,
    ):
        if llm is not None:
            multi = MultiQueryRetriever.from_llm(
                retriever=base_retriever, llm=llm
            )
            extractor = (
                LLMChainExtractor.from_llm(llm) if use_extractor else None
            )
        else:
            multi = None
            extractor = None

        return cls(
            base_retriever=base_retriever,
            llm=llm,
            reranker=reranker,
            extractor=extractor,
            multi_query=multi,
            summarizer_llm=summarizer_llm,
            max_summary_tokens=max_summary_tokens,
            _think_mode=(llm is not None) and think_mode,
        )

    @property
    def think_mode(self) -> bool:
        return self._think_mode

    @think_mode.setter
    def think_mode(self, value: bool):
        self._think_mode = (self.llm is not None) and value

    def populate(
        self,
        chunks: list[Document],
        metadata: dict[str, str],
        parent_ids: list[Document] | None,
        parent_chunks: list[Document] | None,
    ) -> None:
        self.base_retriever.populate(
            chunks, metadata, parent_ids, parent_chunks
        )

    async def apopulate(
        self,
        chunks: list[Document],
        metadata: dict[str, str],
        parent_ids: list[Document] | None,
        parent_chunks: list[Document] | None,
    ) -> None:
        await self.base_retriever.apopulate(
            chunks, metadata, parent_ids, parent_chunks
        )

    def delete_document(self, document_id: str):
        self.base_retriever.delete_document(document_id)

    def retrieve(self, text: str) -> list[Document]:
        return self._get_relevant_documents(text)

    def _get_relevant_documents(self, query: str) -> list[Document]:
        if self._think_mode and self.multi_query is not None:
            docs = self.multi_query.invoke(query)
        else:
            docs = self.base_retriever.invoke(query)

        if self.extractor is not None:
            docs = self.extractor.compress_documents(docs, query=query)

        if self.reranker is not None:
            docs = self.reranker.compress_documents(docs, query=query)

        if self.summarizer_llm:
            docs = self._summarize_if_needed(docs)

        return docs

    async def aretrieve(self, text: str) -> list[Document]:
        return await self._aget_relevant_documents(text)

    async def _aget_relevant_documents(self, query: str) -> list[Document]:
        if self._think_mode and self.multi_query is not None:
            docs = await self.multi_query.ainvoke(query)
        else:
            docs = await self.base_retriever.ainvoke(query)

        if self.extractor is not None:
            docs = await self.extractor.acompress_documents(docs, query=query)

        if self.reranker is not None:
            docs = await self.reranker.acompress_documents(docs, query=query)

        if self.summarizer_llm:
            docs = await self._async_summarize_if_needed(docs)

        return docs

    def _summarize_if_needed(self, docs: list[Document]) -> list[Document]:
        full_text = "\n\n".join(d.page_content for d in docs)

        if len(full_text) < self.max_summary_tokens * 4:
            return docs

        summary = self.summarizer_llm.invoke(
            "Summarize the following context while preserving"
            f" all factual details:\n\n{full_text}"
        )

        return [Document(page_content=summary)]

    async def _async_summarize_if_needed(self, docs: list[Document]):
        full_text = "\n\n".join(d.page_content for d in docs)
        if len(full_text) < self.max_summary_tokens * 4:
            return docs

        summary = await self.summarizer_llm.ainvoke(
            "Summarize the following context while preserving"
            f" all factual details:\n\n{full_text}"
        )
        return [Document(page_content=summary)]
