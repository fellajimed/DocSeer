from fastapi import FastAPI
from pydantic import BaseModel
from docseer.converters import DocConverter

app = FastAPI()
doc_converter = DocConverter()


class DocRequest(BaseModel):
    document: str
    document_id: str


class DocResponse(BaseModel):
    document: str
    document_id: str
    content: str
    metadata: dict


@app.post("/read_document", response_model=DocResponse)
async def read_document(req: DocRequest):
    result = await doc_converter.aconvert(req.document)
    content = result.pop("content", "")
    return {
        "document": req.document,
        "document_id": req.document_id,
        "content": content,
        "metadata": result,
    }
