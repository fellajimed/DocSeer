"""
Celery task: ingest_paper
─────────────────────────
Pipeline: source_path → PDF bytes → Markdown → chunks → embeddings → ChromaDB
Status transitions written back to PostgreSQL at every step.

Worker-level singletons (DocConverter, ParentChildChunker) are cached per
process so Docling models load only once per worker, not once per task.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from langchain_ollama import OllamaEmbeddings

from docseer.chunkers import ParentChildChunker
from docseer.converters import DocConverter
from docseer.databases import ChromaVectorDB, LocalFileStoreDB
from docseer.retrievers import Retriever

from ..celery_app import celery_app
from ..config import get_settings
from ..database import SyncSessionFactory
from ..models.paper import Paper, PaperStatus
from ..services.metadata import grobid_metadata_to_paper

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _converter() -> DocConverter:
    s = get_settings()
    return DocConverter(url=f"{s.grobid_url}/api/processHeaderDocument")


@lru_cache(maxsize=1)
def _chunker() -> ParentChildChunker:
    return ParentChildChunker()


@lru_cache(maxsize=1)
def _retriever() -> Retriever:
    s = get_settings()
    embeddings = OllamaEmbeddings(
        model=s.embedding_model,
        base_url=s.ollama_base_url,
    )
    vector_db = ChromaVectorDB(
        model_embeddings=embeddings,
        batch_size=s.embedding_batch_size,
        chroma_host=s.chroma_host,
        chroma_port=s.chroma_port,
    )
    docstore = LocalFileStoreDB(s.docstore_path)
    return Retriever(
        vector_db=vector_db, docstore=docstore, topk=s.retriever_topk
    )


def _update_status(
    paper_id: uuid.UUID,
    status: PaperStatus,
    **extra: Any,
) -> None:
    with SyncSessionFactory() as session:
        paper = session.get(Paper, paper_id)
        if paper is None:
            return
        paper.status = status  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
        for k, v in extra.items():
            setattr(paper, k, v)
        session.commit()


def _backfill_metadata(
    paper: Paper,
    grobid_raw: dict[str, Any],
) -> dict[str, Any]:
    """Return only the fields that are missing on *paper* from GROBID."""
    meta = grobid_metadata_to_paper(grobid_raw)
    updates: dict[str, Any] = {}
    for field, value in meta.items():
        if value and not getattr(paper, field, None):
            updates[field] = value
    return updates


@celery_app.task(
    bind=True,
    name="tasks.ingest_paper",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def ingest_paper(self, paper_id: str) -> dict[str, Any]:
    """
    Full ingestion pipeline for a paper.

    Steps & progress meta (visible via GET /api/tasks/{task_id}):
      1. loading    – read paper row, validate source_path
      2. converting – PDF/URL → Markdown via Docling + GROBID
      3. chunking   – Markdown → parent/child chunk pairs
      4. embedding  – child chunks → ChromaDB; parent chunks → LocalFileStore
      5. done       – update paper row, return summary
    """
    paper_uuid = uuid.UUID(paper_id)

    def _progress(step: str) -> None:
        self.update_state(
            state="STARTED",
            meta={"step": step, "paper_id": paper_id},
        )

    try:
        _progress("loading")
        with SyncSessionFactory() as session:
            paper = session.get(Paper, paper_uuid)
            if paper is None:
                raise ValueError(f"Paper {paper_id} not found in database")
            if not paper.source_path:
                raise ValueError(
                    f"Paper {paper_id} has no source_path — cannot ingest"
                )
            source_path = str(paper.source_path)

        logger.info("Purging existing embeddings for paper %s", paper_id)
        _retriever().delete_document(paper_id)

        _update_status(paper_uuid, PaperStatus.processing)

        _progress("converting")
        result = asyncio.run(_converter().aconvert(source_path))
        content: str = result.pop("content", "")
        grobid_raw: dict[str, Any] = result

        if not content.strip():
            raise RuntimeError(
                f"Docling returned empty content for {source_path}"
            )

        _progress("chunking")
        chunk_result = _chunker().chunk(content, paper_id)
        chunks = chunk_result["chunks"]
        parent_ids = chunk_result["parent_ids"]
        parent_chunks = chunk_result["parent_chunks"]

        _progress("embedding")
        asyncio.run(
            _retriever().apopulate(
                chunks=chunks,
                metadata={"document_id": paper_id},
                parent_ids=parent_ids,
                parent_chunks=parent_chunks,
            )
        )

        with SyncSessionFactory() as session:
            paper = session.get(Paper, paper_uuid)
            if paper is None:
                raise RuntimeError(f"Paper {paper_id} disappeared mid-task")

            paper.status = PaperStatus.done  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
            paper.chunk_count = len(chunks)  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
            paper.date_processed = datetime.now(timezone.utc)  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
            paper.error_message = None  # type: ignore[assignment]  # ty:ignore[invalid-assignment]

            for field, value in _backfill_metadata(paper, grobid_raw).items():
                setattr(paper, field, value)

            session.commit()

        logger.info("Ingested paper %s — %d chunks", paper_id, len(chunks))
        return {"paper_id": paper_id, "chunk_count": len(chunks)}

    except Exception as exc:
        logger.exception("Ingestion failed for paper %s: %s", paper_id, exc)
        _update_status(
            paper_uuid,
            PaperStatus.failed,
            error_message=str(exc)[:2000],
        )
        raise self.retry(exc=exc)
