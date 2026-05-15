from pydantic import BaseModel


class QueryRequest(BaseModel):
    query: str
    think_mode: bool = False
    paper_ids: list[str] | None = None


class ChatMessage(BaseModel):
    role: str  # "human" | "ai"
    content: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessage]
