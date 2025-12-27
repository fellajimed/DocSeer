from fastapi import FastAPI, Request, Depends
from pydantic import BaseModel
from contextlib import asynccontextmanager
from langchain_core.documents import Document
from docseer.chunkers import ParentChildChunker


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.chunker = ParentChildChunker()
    yield


app = FastAPI(lifespan=lifespan)


def get_chunker(request: Request):
    return request.app.state.chunker


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
    parent_chunks: list[Document] | None
    chunks: list[Document]


@app.post("/chunk", response_model=ChunkResponse)
async def chunk_document(
    req: ChunkRequest, request: Request, chunker=Depends(get_chunker)
):
    result = await chunker.achunk(req.content, req.document_id)
    return {
        "document": req.document,
        "document_id": req.document_id,
        "metadata": req.metadata,
        **result,
    }
