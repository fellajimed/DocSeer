from fastapi import FastAPI, Request, Depends
from pydantic import BaseModel
from contextlib import asynccontextmanager
from docseer.converters import DocConverter


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.doc_converter = DocConverter()
    yield


app = FastAPI(lifespan=lifespan)


def get_doc_converter(request: Request):
    return request.app.state.doc_converter


class DocRequest(BaseModel):
    document: str
    document_id: str


class DocResponse(BaseModel):
    document: str
    document_id: str
    content: str
    metadata: dict


@app.post("/read_document", response_model=DocResponse)
async def read_document(
    req: DocRequest, request: Request, doc_converter=Depends(get_doc_converter)
):
    result = await doc_converter.aconvert(req.document)
    content = result.pop("content", "")
    return {
        "document": req.document,
        "document_id": req.document_id,
        "content": content,
        "metadata": result,
    }
