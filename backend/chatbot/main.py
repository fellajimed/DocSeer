import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from docseer.agents import BasicAgent
from docseer import LLM_MODEL
from docseer.documents import Documents

SERVICE_URLS = {
    "pdf2md": "http://localhost:8001",
    "chunking": "http://localhost:8002",
    "retriever": "http://localhost:8003",
    "chatbot": "http://localhost:8000",
}


app = FastAPI()
documents = Documents()
agent = BasicAgent(LLM_MODEL)


class QueryRequest(BaseModel):
    query: str


class DocRequest(BaseModel):
    doc_path: str


@app.get("/get_agent_history")
def get_agent_chat_history():
    return agent.chat_history


@app.post("/clean_agent_history")
def clean_agent_chat_history():
    agent.clean_chat_history()


@app.get("/get_processed_documents")
def get_processed_documents():
    return documents.cache


@app.post("/process_document")
async def process_document(req: DocRequest):
    """
    Get the chunks from the file, and update the vector DB
    """
    if req.doc_path in documents.cache:
        return {"status": "success", "detail": "document already processed"}

    documents.add_source(req.doc_path)
    payload = {
        "document": req.doc_path,
        "document_id": documents.paths2ids[req.doc_path],
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        try:
            # pdf to markdown
            response = await client.post(
                f"{SERVICE_URLS['pdf2md']}/read_document",
                json=payload,
            )
            response.raise_for_status()
            # markdown to chunks
            response = await client.post(
                f"{SERVICE_URLS['chunking']}/chunk",
                json=response.json(),
            )
            response.raise_for_status()
            # save to vector DB
            response = await client.post(
                f"{SERVICE_URLS['retriever']}/populate",
                json=response.json(),
            )
            response.raise_for_status()
            # update document
            documents.cache_source(req.doc_path)
            return {
                "status": "success",
                "detail": "document processed!",
                **payload,
            }
        except httpx.HTTPStatusError:
            raise HTTPException(status_code=400)
        except httpx.RequestError:
            raise HTTPException(status_code=503)


@app.delete("/delete_document")
async def delete_document(req: DocRequest):
    if req.doc_path not in documents.cache:
        return {"status": "success", "detail": "document not in database"}

    payload = {
        "document": req.doc_path,
        "document_id": documents.cache[req.doc_path],
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        try:
            # remove chunks from DB
            response = await client.post(
                f"{SERVICE_URLS['retriever']}/delete_document",
                json=payload,
            )
            response.raise_for_status()
            # update document
            documents.uncache_source(req.doc_path)
            return {"status": "success", "detail": "document removed!"}
        except httpx.HTTPStatusError:
            raise HTTPException(status_code=400)
        except httpx.RequestError:
            raise HTTPException(status_code=503)


@app.post("/stream")
async def stream(req: QueryRequest):
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        try:
            response = await client.post(
                f"{SERVICE_URLS['retriever']}/retrieve",
                params={"query": req.query},
            )
            response.raise_for_status()
            context = response.text
        except httpx.HTTPStatusError:
            raise HTTPException(status_code=400)
        except httpx.RequestError:
            raise HTTPException(status_code=503)
    return StreamingResponse(
        agent.astream(req.query, [context]), media_type="text/markdown"
    )


@app.post("/invoke")
async def invoke(req: QueryRequest):
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        try:
            response = await client.post(
                f"{SERVICE_URLS['retriever']}/retrieve",
                params={"query": req.query},
            )
            response.raise_for_status()
            context = response.text
        except httpx.HTTPStatusError:
            raise HTTPException(status_code=400)
        except httpx.RequestError:
            raise HTTPException(status_code=503)
    response = await agent.ainvoke(req.query, [context])
    return {"response": response}
