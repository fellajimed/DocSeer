from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ..models.paper import PaperStatus


class PaperCreate(BaseModel):
    source_path: str | None = None
    title: str | None = None
    authors: list[str] = []
    abstract: str | None = None
    year: int | None = None
    journal: str | None = None
    publisher: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    isbn: str | None = None
    bibtex_key: str | None = None
    bibtex_raw: str | None = None
    collection: str | None = None
    tags: list[str] = []
    extra_metadata: dict[str, Any] = {}


class PaperRead(BaseModel):
    id: uuid.UUID
    source_path: str | None
    title: str | None
    authors: list[str] | None
    abstract: str | None
    year: int | None
    journal: str | None
    publisher: str | None
    doi: str | None
    arxiv_id: str | None
    url: str | None
    isbn: str | None
    bibtex_key: str | None
    collection: str | None
    tags: list[str] | None
    status: PaperStatus
    error_message: str | None
    chunk_count: int | None
    celery_task_id: str | None
    date_added: datetime
    date_processed: datetime | None
    extra_metadata: dict[str, Any] | None

    model_config = {"from_attributes": True}


class PaperUpdate(BaseModel):
    title: str | None = None
    authors: list[str] | None = None
    abstract: str | None = None
    year: int | None = None
    journal: str | None = None
    publisher: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    collection: str | None = None
    tags: list[str] | None = None
    extra_metadata: dict[str, Any] | None = None


class BibtexImportRequest(BaseModel):
    bibtex: str
    # set True to queue PDF ingestion using the path/URL embedded in bibtex
    trigger_ingest: bool = False


class UrlImportRequest(BaseModel):
    url: str
    trigger_ingest: bool = True


class IngestRequest(BaseModel):
    # override source_path if not already set on the paper
    source_path: str | None = None


class IngestResponse(BaseModel):
    paper_id: uuid.UUID
    task_id: str
    status: str = "queued"
