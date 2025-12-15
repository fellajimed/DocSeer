"""
* ChromaDB
* LocalStore
* OllamaEmbedding
* all relevant service .. as routers ?
"""

from fastapi import FastAPI
from pydantic import BaseModel
from langchain_core.documents import Document
from docseer import retrievers
from docseer import MODEL_EMBEDDINGS, CACHE_FOLDER, SMALL_LLM_MODEL
from docseer.databases import ChromaVectorDB, LocalFileStoreDB
from docseer.agents.utils import docs_to_md

app = FastAPI()


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


docstore = LocalFileStoreDB(CACHE_FOLDER / "docstore_db")
vector_db = ChromaVectorDB(MODEL_EMBEDDINGS, 32, CACHE_FOLDER / "embeds_db")

base_retriever = retrievers.Retriever(
    vector_db=vector_db, docstore=docstore, topk=2
)
retriever = retrievers.MultiStepsRetriever.init(
    base_retriever=base_retriever, llm=SMALL_LLM_MODEL
)


@app.post("/populate", response_model=RetrieverResponse)
async def populate_db(req: RetrieverRequest):
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
def delete_document(req: RetrieverResponse):
    retriever.delete_document(document_id=req.document_id)
    return {
        "document": req.document,
        "document_id": req.document_id,
    }


@app.post("/retrieve")
async def retrieve(query: str) -> str:
    context = await retriever.aretrieve(query)
    return docs_to_md(context)
