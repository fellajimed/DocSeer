from typing import Any
from pydantic import Field
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_classic.retrievers.document_compressors import LLMChainExtractor


class MultiStepsRetriever(BaseRetriever):
    base_retriever: BaseRetriever = Field(...)
    llm: Any = Field(None)
    reranker: Any = Field(None)
    extractor: LLMChainExtractor | None = Field(None)
    multi_query: MultiQueryRetriever | None = Field(None)
    summarizer_llm: Any = Field(None)
    max_summary_tokens: int = 2048

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def init(
        cls,
        base_retriever: BaseRetriever,
        llm=None,
        reranker=None,
        summarizer_llm=None,
        max_summary_tokens=2048,
    ):
        if llm is not None:
            multi = MultiQueryRetriever.from_llm(
                retriever=base_retriever, llm=llm
            )
            extractor = LLMChainExtractor.from_llm(llm)
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
        )

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

    def retrieve(self, text: str) -> list[Document]:
        return self._get_relevant_documents(text)

    def _get_relevant_documents(self, query: str) -> list[Document]:
        if self.multi_query is not None:
            docs = self.multi_query.invoke(query)
        else:
            docs = self.base_retriever.invoke(query)

        if self.extractor is not None:
            docs = self.extractor.compress_documents(docs, query=query)

        if self.reranker is not None:
            docs = self.reranker.rerank(
                query=query,
                documents=docs,
                top_k=len(docs),
            )
            docs = [doc for doc, _ in docs]

        if self.summarizer_llm:
            docs = self._summarize_if_needed(docs)

        return docs

    async def aretrieve(self, text: str) -> list[Document]:
        return await self._aget_relevant_documents(text)

    async def _aget_relevant_documents(self, query: str) -> list[Document]:
        if self.multi_query is not None:
            docs = await self.multi_query.ainvoke(query)
        else:
            docs = await self.base_retriever.ainvoke(query)

        if self.extractor is not None:
            docs = await self.extractor.acompress_documents(docs, query=query)

        if self.reranker is not None:
            docs = await self.reranker.arerank(
                query=query,
                documents=docs,
                top_k=len(docs),
            )
            docs = [doc for doc, _ in docs]

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


"""

from langchain_openai import ChatOpenAI
from my_reranker import MyReranker  # your reranker implementation

llm = ChatOpenAI(model="gpt-4.1")
summ_llm = ChatOpenAI(model="gpt-4.1-mini")
reranker = MyReranker()

smart_ret = SmartRetriever.from_components(
    base_retriever=my_vector_retriever,
    llm=llm,
    reranker=reranker,
    summarizer_llm=summ_llm,
    max_summary_tokens=2048,
)

docs = smart_ret.get_relevant_documents("Explain quantum transformers")

"""
