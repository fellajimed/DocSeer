from typing import Optional
from dataclasses import dataclass
from rich.console import Console
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from langchain_core.vectorstores import VectorStoreRetriever

from .base_agent import BaseAgent

# DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/v1"
DEFAULT_OLLAMA_URL = "http://localhost:11434/v1"

AGENT_TEMPLATE = """\
You are an exeprt in answering questions about reseach papers.
Use the following relevant context to answer the question.
If you don't know the answer, just say that you don't know.
Make sure to cite the source documents if you can.
If you are confident, generate the final answer without repeating tool use.
When you do not need to use a tool, answer directly.
Do not review the same document more than once.
"""


class RAGAnswer(BaseModel):
    """Structured response for a RAG question."""
    response: str = Field(
        description="The final answer based on the retrieved context.")


@dataclass
class Deps:
    retriever: VectorStoreRetriever


class PydanticAIDocAgent(BaseAgent):
    def __init__(self, text_embedder) -> None:
        ollama_model = OpenAIChatModel(
            model_name='llama3.2',
            provider=OpenAIProvider(base_url=DEFAULT_OLLAMA_URL),
        )
        self.agent = Agent(
            ollama_model,
            system_prompt=AGENT_TEMPLATE,
            deps_type=Deps,
            output_type=str,
        )

        self.deps = Deps(text_embedder.invoke)

        @self.agent.tool_plain
        def list_documents_titles() -> str:
            """
            List the titles of all the documents provided by the user.
            """
            collection = text_embedder.vector_db._collection
            metadatas = collection.get(include=["metadatas"])["metadatas"]

            unique_titles = {meta["title"] for meta in metadatas
                             if meta and "title" in meta}
            response = "\n\n---\n\n".join(
                f"{i+1}. {title}" for i, title in enumerate(unique_titles)
            )

            return response

        @self.agent.tool
        def retrieve_context(ctx: RunContext[Deps], query: str,
                             file_index: Optional[int] = None) -> str:
            """
            Searches and retrieves relevant document to answer user
            questions about research papers.
            Use this tool to find factual information, definitions,
            or specific details.
            If the user asks about a specific file, defined by its index
            `file_index`, apply a filter to invoke.
            If the information is to be retrieved from all the documents,
            set `file_index` to None.
            """
            kwargs = dict()
            if file_index is not None:
                kwargs['filter'] = {'file_index': file_index}
            c = f"Context:\n{ctx.deps.retriever(query, **kwargs)}"
            # c = f"Context:\n{text_embedder.invoke(query, **kwargs)}"
            return c

        self.message_history = None

    def retrieve(self, query: str) -> str:
        with Console().status('', spinner='dots'):
            result = self.agent.run_sync(
                query, message_history=self.message_history,
                deps=self.deps,
            )
            self.message_history = result.new_messages()
            return result.output
