from fastapi import FastAPI
from pydantic import BaseModel
from docseer.chunkers import ParentChildChunker

app = FastAPI()
chunker = ParentChildChunker()


class ChunkRequest(BaseModel):
    document: str
    document_id: str
    content: str
    metadata: dict


class ChunkResponse(BaseModel):
    document: str
    document_id: str
    metadata: dict
    parent_ids: list[str] | None
    parent_chunks: list[str] | None
    chunks: list[str]


@app.post("/chunk", response_model=ChunkResponse)
async def chunk_document(req: ChunkRequest):
    result = await chunker.achunk(req.content, req.document_id)
    return {
        "document": req.document,
        "document_id": req.document_id,
        "metadata": req.metadata,
        **result,
    }
