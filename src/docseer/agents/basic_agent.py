from rich.console import Console
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from .utils import docs_to_md


SYSTEM_TEMPLATE = """\
You are an expert in answering questions about research papers.

You always consider the entire conversation history when interpreting the
user's latest question. If the user uses pronouns or phrases like
"explain it", "go deeper", "what about that result", etc., resolve those
references using previous messages.

If the answer cannot be derived from the context or conversation history,
say that you don't know.
"""


HUMAN_TEMPLATE = """\
Use the following retrieved context and the conversation history to answer
the question.

- If the user's question refers to earlier topics (e.g. "explain it"),
  you must infer the referent from the chat history.
- Always cite the source documents from the context when they contribute
  to your answer.

----------------Context:
{context}

----------------User Question:
{question}
"""


class BasicAgent:
    def __init__(self, llm_model, max_turns: int | None = None):
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
        self.max_turns = max_turns

    def clean_chat_history(self):
        self.chat_history = ChatMessageHistory()

    def _update_chat_history(self, query: str, response: str):
        self.chat_history.add_message(HumanMessage(content=query))
        self.chat_history.add_message(AIMessage(content=response))
        if self.max_turns is not None:
            self.chat_history = self.chat_history[-2 * self.max_turns :]

    def stream(self, query: str, context: list[str | Document]):
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

        self._update_chat_history(query, response)

    async def astream(self, query: str, context: list[str | Document]):
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

        self._update_chat_history(query, response)

    def invoke(self, query: str, context: list[str | Document]) -> str:
        context_md = docs_to_md(context)
        with Console().status("", spinner="dots"):
            response = self.chain.invoke(
                {
                    "context": context_md,
                    "question": query,
                    "chat_history": self.chat_history.messages,
                }
            )

            self._update_chat_history(query, response)
            return response

    async def ainvoke(self, query: str, context: list[str | Document]) -> str:
        context_md = docs_to_md(context)
        with Console().status("", spinner="dots"):
            response = await self.chain.ainvoke(
                {
                    "context": context_md,
                    "question": query,
                    "chat_history": self.chat_history.messages,
                }
            )

            self._update_chat_history(query, response)
            return response
