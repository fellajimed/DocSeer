import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from docseer.agents import BasicAgent
from docseer import LLM_MODEL
import requests

app = FastAPI()

RETRIEVER_ENDPOINT = "http://localhost:8003"

agent = BasicAgent(LLM_MODEL)


class QueryRequest(BaseModel):
    query: str


@app.post("/stream")
def stream(req: QueryRequest):
    try:
        response = requests.post(
            f"{RETRIEVER_ENDPOINT}/retrieve",
            params={"query": req.query},
        )
        response.raise_for_status()
        context = response.text
    except Exception:
        raise HTTPException(status_code=503)
    return StreamingResponse(
        agent.stream(req.query, context), media_type="text/markdown"
    )


@app.post("/astream")
async def astream(req: QueryRequest):
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        try:
            response = await client.post(
                f"{RETRIEVER_ENDPOINT}/retrieve",
                params={"query": req.query},
            )
            response.raise_for_status()
            context = response.text
        except httpx.HTTPStatusError:
            raise HTTPException(status_code=400)
        except httpx.RequestError:
            raise HTTPException(status_code=503)
    return StreamingResponse(
        agent.astream(req.query, context), media_type="text/markdown"
    )


@app.post("/invoke")
def invoke(req: QueryRequest):
    try:
        response = requests.post(
            f"{RETRIEVER_ENDPOINT}/retrieve",
            params={"query": req.query},
        )
        response.raise_for_status()
        context = response.text
    except Exception:
        raise HTTPException(status_code=503)
    return agent.invoke(req.query, context)


@app.post("/ainvoke")
async def ainvoke(req: QueryRequest):
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        try:
            response = await client.post(
                f"{RETRIEVER_ENDPOINT}/retrieve",
                params={"query": req.query},
            )
            response.raise_for_status()
            context = response.text
        except httpx.HTTPStatusError:
            raise HTTPException(status_code=400)
        except httpx.RequestError:
            raise HTTPException(status_code=503)
    return await agent.ainvoke(req.query, context)
