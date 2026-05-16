from pydantic import BaseModel


class QueryRequest(BaseModel):
    query: str
    think_mode: bool = False
    paper_ids: list[str] | None = None
    topk: int = 5


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessage]
