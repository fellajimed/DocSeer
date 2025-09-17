from rich.console import Console
from langchain_ollama.llms import OllamaLLM
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from .base_agent import BaseAgent

SYSTEM_TEMPLATE = """\
You are an exeprt in answering questions about reseach papers.
If you don't know the answer, just say that you don't know.
"""

HUMAN_TEMPLATE = """\
Use the following relevant context to answer the question.
Make sure to cite the source documents if you can.

----------------Context:
{context}

----------------Question:
{question}
"""


class LocalDocAgent(BaseAgent):
    def __init__(self, text_embedder):
        self.template = SYSTEM_TEMPLATE

        self.model = OllamaLLM(model="llama3.2")
        self.prompt = ChatPromptTemplate([
            ("system", SYSTEM_TEMPLATE),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", HUMAN_TEMPLATE),
        ])
        self.chain = self.prompt | self.model

        self.chat_history = []

        self.text_embedder = text_embedder

    def retrieve(self, query: str) -> str:
        with Console().status('', spinner='dots'):
            context = self.text_embedder.invoke(query)
            response = self.chain.invoke({
                "context": context,
                "question": query,
                "chat_history": self.chat_history,
            })
            self.chat_history.extend([
                HumanMessage(content=query),
                AIMessage(content=response),
            ])
            return response
