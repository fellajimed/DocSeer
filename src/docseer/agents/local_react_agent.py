import contextlib
from rich.console import Console
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool
from langchain.memory import ConversationBufferMemory
from langchain.agents import AgentExecutor, create_react_agent

from .base_agent import Agent
from .callback_handlers import RichCallbackHandler


AGENT_TEMPLATE = """\
You are an expert in answering questions about research papers.
You have access to the following tool:

{tools}

To use a tool, you must follow this format:
```
Thought: Do I need to use a tool? Yes.
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Observation can repeat
 until you have a final answer)
Thought: I have enough information to answer the question.
Final Answer: [your final answer here]
```

When you do not need to use a tool, answer directly.
Begin!

Chat History:
{chat_history}
Question: {question}
{agent_scratchpad}
"""


class LocalDocReActAgent(Agent):
    """
    An agentic RAG system for answering questions about research papers.

    This agent can intelligently decide when to retrieve context from
    a knowledge base before answering a user's question.
    """

    def __init__(self, text_embedder, verbose=True):
        self.template = AGENT_TEMPLATE

        @tool
        def retrieve_document_context(query: str) -> str:
            """
            Searches and retrieves relevant document excerpts to answer user
            questions about research papers.
            Use this tool to find factual information, definitions,
            or specific details.
            """
            return text_embedder.invoke(query)

        @tool
        def check_history_relevance(new_input: str) -> str:
            """
            Analyzes the chat history to determine if it is relevant to
            the new user input.
            Use this tool to decide if you need to perform a new search.
            Returns 'yes' if the history is relevant, 'no' otherwise.
            """
            # Use a lightweight LLM to check relevance.
            relevance_llm = OllamaLLM(model="llama3.2")
            relevance_prompt = PromptTemplate.from_template(
                "Based on the chat history below, "
                "is the new user input about a related topic? "
                "Respond with 'yes' or 'no' only."
                "\n\nChat History:\n{history}\n\nNew Input:{input}"
            )
            # We use the raw buffer string for a simple, quick check.
            response = relevance_llm.invoke(relevance_prompt.format(
                history=self.memory.buffer,
                input=new_input
            ))
            return response.strip().lower()

        self.tools = [retrieve_document_context, check_history_relevance]

        # Create the LangChain PromptTemplate and the LLM.
        self.prompt = PromptTemplate.from_template(self.template)
        self.llm = OllamaLLM(model="llama3.2")
        self.verbose = verbose

        self.agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.prompt
        )

        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=False,
            handle_parsing_errors=True,
            callbacks=[RichCallbackHandler()] if verbose else [],
        )

        self.memory = ConversationBufferMemory(return_messages=True)

    def retrieve(self, query: str, verbose: bool = False) -> str:
        """
        Invokes the agent to process the query and provides the final answer.
        """
        cm = (contextlib.nullcontext() if self.verbose
              else Console().status('', spinner='dots'))
        with cm:
            try:
                response = self.agent_executor.invoke({
                    "question": query,
                    "chat_history": self.memory.buffer_as_messages,
                })["output"]

                self.memory.save_context(
                    {"question": query}, {"output": response})

                return response
            except Exception as e:
                # Handle potential errors during execution
                return f"An error occurred: {e}"
