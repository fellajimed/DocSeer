from rich.console import Console
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from .utils import docs_to_md


SYSTEM_TEMPLATE = """\
You are an expert in answering questions about reseach papers.
If you don't know the answer, just say that you don't know.
"""

HUMAN_TEMPLATE = """\
Use the following relevant context to answer the question.
Make sure to cite the source documents.

----------------Context:
{context}

----------------Question:
{question}
"""


class BasicAgent:
    def __init__(self, llm_model):
        self.template = SYSTEM_TEMPLATE

        self.model = llm_model
        self.prompt = ChatPromptTemplate(
            [
                ("system", SYSTEM_TEMPLATE),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", HUMAN_TEMPLATE),
            ]
        )
        self.chain = self.prompt | self.model

        self.chat_history = ChatMessageHistory()

    def stream(self, query: str, context: list[Document]):
        context_md = docs_to_md(context)
        it = self.chain.stream(
            {
                "context": context_md,
                "question": query,
                "chat_history": self.chat_history.messages,
            }
        )

        response = ""
        for chunk in it:
            response += chunk
            yield chunk

        self.chat_history.add_message(HumanMessage(content=query))
        self.chat_history.add_message(AIMessage(content=response))

    async def astream(self, query: str, context: list[Document]):
        context_md = docs_to_md(context)
        ait = self.chain.astream(
            {
                "context": context_md,
                "question": query,
                "chat_history": self.chat_history.messages,
            }
        )

        response = ""
        async for chunk in ait:
            response += chunk
            yield chunk

        self.chat_history.add_message(HumanMessage(content=query))
        self.chat_history.add_message(AIMessage(content=response))

    def invoke(self, query: str, context: list[Document]) -> str:
        context_md = docs_to_md(context)
        with Console().status("", spinner="dots"):
            response = self.chain.invoke(
                {
                    "context": context_md,
                    "question": query,
                    "chat_history": self.chat_history.messages,
                }
            )

            self.chat_history.add_message(HumanMessage(content=query))
            self.chat_history.add_message(AIMessage(content=response))

            return response

    async def ainvoke(self, query: str, context: list[Document]) -> str:
        context_md = docs_to_md(context)
        with Console().status("", spinner="dots"):
            response = await self.chain.ainvoke(
                {
                    "context": context_md,
                    "question": query,
                    "chat_history": self.chat_history.messages,
                }
            )

            self.chat_history.add_message(HumanMessage(content=query))
            self.chat_history.add_message(AIMessage(content=response))

            return response
