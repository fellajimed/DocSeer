from typing import Any
from pydantic import Field
from langchain_ollama.llms import OllamaLLM
from langchain_core.retrievers import BaseRetriever
from langchain_classic.retrievers.multi_query import MultiQueryRetriever


LLM_MODEL = OllamaLLM(model="llama3.2")


class One2ManyQueriesRetriever(BaseRetriever):
    base_retriever: Any = Field(...)
    llm_model: Any = Field(...)
    retriever: MultiQueryRetriever = Field(...)

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def init(cls, base_retriever, llm_model=LLM_MODEL):
        mq = MultiQueryRetriever.from_llm(
            retriever=base_retriever,
            llm=llm_model,
        )
        return cls(
            base_retriever=base_retriever,
            llm_model=llm_model,
            retriever=mq,
        )

    def retrieve(self, text: str):
        return self.retriever.invoke(text)

    def _get_relevant_documents(self, text: str):
        return self.retrieve(text)

    async def aretrieve(self, text: str):
        return await self.retriever.ainvoke(text)

    async def _aget_relevant_documents(self, text: str):
        return await self.aretrieve(text)
