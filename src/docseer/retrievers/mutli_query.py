from typing import Any
from pydantic import ConfigDict, Field
from langchain_ollama.llms import OllamaLLM
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_classic.retrievers.multi_query import MultiQueryRetriever


LLM_MODEL = OllamaLLM(model="llama3.2:3b")


class One2ManyQueriesRetriever(BaseRetriever):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    base_retriever: Any = Field(...)
    llm_model: Any = Field(...)
    retriever: MultiQueryRetriever = Field(...)

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

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ):
        return self.retrieve(query)

    async def aretrieve(self, text: str):
        return await self.retriever.ainvoke(text)

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: AsyncCallbackManagerForRetrieverRun,
    ):
        return await self.aretrieve(query)
