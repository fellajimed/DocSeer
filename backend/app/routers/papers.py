from __future__ import annotations

import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db
from ..models.paper import Paper, PaperStatus
from ..schemas.paper import (
    BibtexImportRequest,
    IngestRequest,
    IngestResponse,
    PaperCreate,
    PaperRead,
    PaperUpdate,
    UrlImportRequest,
)
from ..services.ingest import delete_paper_embeddings
from ..services.metadata import fetch_metadata_from_url, parse_bibtex
from ..tasks.ingest import ingest_paper
from ..config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/papers", tags=["papers"])
DB = Annotated[AsyncSession, Depends(get_db)]

# Stable namespace for source-path-derived UUIDs (RFC 4122 §4.3)
_NS = uuid.NAMESPACE_URL


def _source_uuid(source_path: str) -> uuid.UUID:
    """Deterministic UUID v5 derived from source_path.

    Two calls with the same path always return the same UUID, so duplicate
    inserts simply hit a primary-key conflict rather than creating duplicates.
    """
    return uuid.uuid5(_NS, source_path)


# ── helpers ───────────────────────────────────────────────────────────────────


def _dispatch(paper: Paper) -> IngestResponse:
    """Fire-and-forget ingest task, update paper.celery_task_id in place."""
    task = ingest_paper.apply_async(args=[str(paper.id)], queue="ingest")
    paper.celery_task_id = task.id
    paper.status = PaperStatus.pending
    return IngestResponse(paper_id=paper.id, task_id=task.id, status="queued")


async def _get_or_404(db: AsyncSession, paper_id: uuid.UUID) -> Paper:
    paper = await db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


# ── list / get ────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[PaperRead])
async def list_papers(db: DB):
    rows = await db.execute(select(Paper).order_by(Paper.date_added.desc()))
    return rows.scalars().all()


@router.get("/{paper_id}", response_model=PaperRead)
async def get_paper(paper_id: uuid.UUID, db: DB):
    return await _get_or_404(db, paper_id)


# ── create / ingest ───────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def add_paper(body: PaperCreate, db: DB):
    """
    Create a paper record and immediately queue ingestion if a source_path
    is provided.  Returns 202 with the Celery task_id to poll.

    Dedup: when source_path is given its UUID5 is used as the primary key.
    A duplicate insert hits the PK conflict and returns 200 with
    status="already_ingested" instead of creating a duplicate.
    """
    paper_id = (
        _source_uuid(body.source_path) if body.source_path else uuid.uuid4()
    )
    paper = Paper(id=paper_id, **body.model_dump())
    db.add(paper)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        # Try PK lookup first (fast path: same source_path → same UUID5).
        existing = await db.get(Paper, paper_id)
        if existing is None:
            # Conflict came from the source_path UNIQUE constraint against a
            # row that was inserted before the UUID5 migration (different id).
            result = await db.execute(
                select(Paper).where(Paper.source_path == body.source_path)
            )
            existing = result.scalar_one()
        logger.info(
            "Paper with source_path %r already exists (id=%s, status=%s) — skipping",
            body.source_path,
            existing.id,
            existing.status,
        )
        return JSONResponse(
            status_code=200,
            content=IngestResponse(
                paper_id=existing.id,
                task_id=existing.celery_task_id or "",
                status="already_ingested",
            ).model_dump(mode="json"),
        )

    if paper.source_path:
        await db.commit()  # row must be visible to the worker before we queue
        resp = _dispatch(paper)
        await db.commit()  # persist celery_task_id + status=pending
        return resp

    paper.status = PaperStatus.metadata_only
    await db.commit()
    return IngestResponse(
        paper_id=paper.id, task_id="", status="metadata_only"
    )


@router.post(
    "/import-bibtex",
    response_model=list[IngestResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_bibtex(body: BibtexImportRequest, db: DB):
    """
    Parse a Zotero BibTeX export and create one Paper per entry.
    Skips entries whose bibtex_key already exists in the database.
    If trigger_ingest=true, queues ingestion for any entry that has a
    file path embedded in the BibTeX 'file' field.
    """
    entries = parse_bibtex(body.bibtex)
    responses: list[IngestResponse] = []

    for entry in entries:
        # dedup by bibtex_key
        if entry.get("bibtex_key"):
            existing = await db.execute(
                select(Paper).where(Paper.bibtex_key == entry["bibtex_key"])
            )
            if existing.scalar_one_or_none():
                logger.debug(
                    "Skipping duplicate bibtex_key %s", entry["bibtex_key"]
                )
                continue

        paper = Paper(
            status=PaperStatus.metadata_only,
            **{k: v for k, v in entry.items() if hasattr(Paper, k)},
        )
        db.add(paper)
        await db.flush()
        await db.commit()  # row must exist before the task can read it

        if body.trigger_ingest and paper.source_path:
            resp = _dispatch(paper)
            await db.commit()  # persist celery_task_id + status=pending
        else:
            resp = IngestResponse(
                paper_id=paper.id, task_id="", status="metadata_only"
            )
        responses.append(resp)

    return responses


@router.post(
    "/import-url",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_from_url(body: UrlImportRequest, db: DB):
    """
    Resolve a URL via the Zotero Translation Server, create a paper record
    with the returned metadata, and optionally queue ingestion.
    """
    settings = get_settings()
    meta = await fetch_metadata_from_url(body.url, settings.zotero_url) or {}
    meta.setdefault("url", body.url)
    meta.setdefault("source_path", body.url)

    paper = Paper(
        status=PaperStatus.metadata_only,
        **{k: v for k, v in meta.items() if hasattr(Paper, k)},
    )
    db.add(paper)
    await db.flush()

    if body.trigger_ingest:
        await db.commit()  # row must be visible to the worker before we queue
        resp = _dispatch(paper)
        await db.commit()  # persist celery_task_id + status=pending
    else:
        resp = IngestResponse(
            paper_id=paper.id, task_id="", status="metadata_only"
        )

    if not body.trigger_ingest:
        await db.commit()
    return resp


@router.post(
    "/{paper_id}/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_ingest(paper_id: uuid.UUID, body: IngestRequest, db: DB):
    """(Re-)trigger ingestion for an existing paper."""
    paper = await _get_or_404(db, paper_id)

    if paper.status == PaperStatus.processing:
        raise HTTPException(
            status_code=409, detail="Paper is currently being processed"
        )

    if body.source_path:
        paper.source_path = body.source_path

    if not paper.source_path:
        raise HTTPException(
            status_code=422,
            detail="No source_path on record — provide one in the request body",
        )

    paper.error_message = None
    resp = _dispatch(paper)
    await db.commit()
    return resp


# ── update / delete ───────────────────────────────────────────────────────────


@router.put("/{paper_id}", response_model=PaperRead)
async def update_paper(paper_id: uuid.UUID, body: PaperUpdate, db: DB):
    paper = await _get_or_404(db, paper_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(paper, field, value)
    await db.commit()
    await db.refresh(paper)
    return paper


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_paper(
    paper_id: uuid.UUID, background_tasks: BackgroundTasks, db: DB
):
    paper = await _get_or_404(db, paper_id)
    pid = str(paper.id)
    had_embeddings = paper.status == PaperStatus.done
    await db.delete(paper)
    await db.commit()
    # clean up vectors + docstore without blocking the response
    if had_embeddings:
        background_tasks.add_task(delete_paper_embeddings, pid)
