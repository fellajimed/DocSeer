"""
* ChromaDB
* LocalStore
* OllamaEmbedding
* all relevant service .. as routers ?
"""

from pathlib import Path
from fastapi import FastAPI, Request, Depends
from pydantic import BaseModel
from contextlib import asynccontextmanager
from langchain_core.documents import Document
from langchain_ollama.llms import OllamaLLM
from langchain_ollama import OllamaEmbeddings
from docseer import retrievers
from docseer import CACHE_FOLDER
from docseer.databases import ChromaVectorDB, LocalFileStoreDB
from docseer.agents.utils import docs_to_md
from docseer.config import read_config, get_main_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    config_path = (
        Path(__file__).resolve().absolute().parents[1] / "config.yaml"
    )
    config = get_main_config(read_config(config_path))

    model_embeddings = OllamaEmbeddings(**config["model_embeddings"])
    small_llm_model = (
        None
        if config.get("small_llm_model") is None
        else OllamaLLM(**config["small_llm_model"])
    )

    batch_size = config.get("chromavectordb", dict()).get("batch_size", 128)
    docstore = LocalFileStoreDB(CACHE_FOLDER / "docstore_db")
    vector_db = ChromaVectorDB(
        model_embeddings, batch_size, CACHE_FOLDER / "embeds_db"
    )

    topk = config.get("retriever", dict()).get("topk", 3)
    base_retriever = retrievers.Retriever(
        vector_db=vector_db, docstore=docstore, topk=topk
    )
    app.state.retriever = retrievers.MultiStepsRetriever.init(
        base_retriever=base_retriever, llm=small_llm_model
    )
    yield


app = FastAPI(lifespan=lifespan)


def get_retriever(request: Request):
    return request.app.state.retriever


class RetrieverRequest(BaseModel):
    document: str
    document_id: str
    metadata: dict
    parent_ids: list[str] | None
    parent_chunks: list[Document] | None
    chunks: list[Document]


class RetrieverResponse(BaseModel):
    document: str
    document_id: str


@app.post("/populate", response_model=RetrieverResponse)
async def populate_db(
    req: RetrieverRequest, request: Request, retriever=Depends(get_retriever)
):
    await retriever.apopulate(
        chunks=req.chunks,
        metadata=req.metadata,
        parent_ids=req.parent_ids,
        parent_chunks=req.parent_chunks,
    )
    return {
        "document": req.document,
        "document_id": req.document_id,
    }


@app.post("/delete_document")
def delete_document(
    req: RetrieverResponse, request: Request, retriever=Depends(get_retriever)
):
    retriever.delete_document(document_id=req.document_id)
    return {
        "document": req.document,
        "document_id": req.document_id,
    }


@app.post("/retrieve")
async def retrieve(
    query: str, request: Request, retriever=Depends(get_retriever)
) -> str:
    context = await retriever.aretrieve(query)
    return docs_to_md(context)
