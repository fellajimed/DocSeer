from __future__ import annotations

import re
import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
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

_NS = uuid.NAMESPACE_URL

_ARXIV_PDF_RE = re.compile(r"https?://arxiv\.org/pdf/(\d+\.\d+(?:v\d+)?)")
_ARXIV_ABS_RE = re.compile(r"https?://arxiv\.org/abs/(\d+\.\d+(?:v\d+)?)")


def _arxiv_abstract_url(url: str) -> str:
    m = _ARXIV_PDF_RE.match(url)
    if m:
        return f"https://arxiv.org/abs/{m.group(1)}"
    return url


def _arxiv_pdf_url(url: str) -> str:
    m = _ARXIV_ABS_RE.match(url)
    if m:
        return f"https://arxiv.org/pdf/{m.group(1)}"
    return url


def _source_uuid(source_path: str) -> uuid.UUID:
    """Deterministic UUID v5 derived from source_path.

    Two calls with the same path always return the same UUID, so duplicate
    inserts simply hit a primary-key conflict rather than creating duplicates.
    """
    return uuid.uuid5(_NS, source_path)


def _dispatch(paper: Paper) -> IngestResponse:
    """Fire-and-forget ingest task, update paper.celery_task_id in place."""
    task = ingest_paper.apply_async(args=[str(paper.id)], queue="ingest")
    paper.celery_task_id = task.id  # type: ignore[assignment]
    paper.status = PaperStatus.pending  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
    return IngestResponse(paper_id=paper.id, task_id=task.id, status="queued")  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]


async def _get_or_404(db: AsyncSession, paper_id: uuid.UUID) -> Paper:
    paper = await db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.get("/", response_model=list[PaperRead])
async def list_papers(db: DB):
    rows = await db.execute(select(Paper).order_by(Paper.date_added.desc()))
    return rows.scalars().all()


@router.get("/{paper_id}", response_model=PaperRead)
async def get_paper(paper_id: uuid.UUID, db: DB):
    return await _get_or_404(db, paper_id)


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
        existing = await db.get(Paper, paper_id)
        if existing is None:
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
                paper_id=existing.id,  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
                task_id=existing.celery_task_id or "",  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
                status="already_ingested",
            ).model_dump(mode="json"),
        )

    if paper.source_path:
        await db.commit()
        resp = _dispatch(paper)
        await db.commit()
        return resp

    paper.status = PaperStatus.metadata_only  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
    await db.commit()
    return IngestResponse(
        paper_id=paper.id,  # ty:ignore[invalid-argument-type]
        task_id="",
        status="metadata_only",  # type: ignore[arg-type]
    )


@router.post(
    "/import-bibtex",
    response_model=list[IngestResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_bibtex(body: BibtexImportRequest, db: DB):
    """
    Parse a BibTeX export and create one Paper per entry.
    Matches existing papers by bibtex_key, source_path, or DOI and
    populates their metadata from BibTeX fields (BibTeX is trusted as correct).
    If trigger_ingest=true and the entry has a source_path, queues ingestion;
    otherwise the paper is created with status=metadata_only.
    """
    entries = parse_bibtex(body.bibtex)
    responses: list[IngestResponse] = []

    for entry in entries:
        paper = None

        match_conditions = []
        if entry.get("bibtex_key"):
            match_conditions.append(Paper.bibtex_key == entry["bibtex_key"])
        if entry.get("source_path"):
            match_conditions.append(Paper.source_path == entry["source_path"])
        if entry.get("doi"):
            match_conditions.append(Paper.doi == entry["doi"])

        if match_conditions:
            existing = await db.execute(
                select(Paper).where(or_(*match_conditions))
            )
            paper = existing.scalar_one_or_none()

        if paper is not None:
            for field in entry:
                if hasattr(Paper, field) and entry[field] is not None:
                    if field == "extra_metadata":
                        existing_extra = paper.extra_metadata or {}
                        existing_extra.update(entry["extra_metadata"])
                        paper.extra_metadata = existing_extra  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
                    elif field == "source_path":
                        if not paper.source_path:
                            paper.source_path = str(entry["source_path"])  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
                    elif field not in (
                        "status",
                        "error_message",
                        "chunk_count",
                        "celery_task_id",
                        "date_added",
                        "date_processed",
                        "id",
                    ):
                        setattr(paper, field, entry[field])
            await db.commit()
        else:
            paper = Paper(
                status=PaperStatus.metadata_only,
                **{k: v for k, v in entry.items() if hasattr(Paper, k)},
            )
            db.add(paper)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                existing = await db.execute(
                    select(Paper).where(
                        Paper.source_path == entry.get("source_path")
                    )
                )
                paper = existing.scalar_one_or_none()
                if paper is None:
                    continue
                for field in entry:
                    if (
                        hasattr(Paper, field)
                        and entry[field] is not None
                        and field
                        not in (
                            "status",
                            "error_message",
                            "chunk_count",
                            "celery_task_id",
                            "date_added",
                            "date_processed",
                            "id",
                            "source_path",
                        )
                    ):
                        setattr(paper, field, entry[field])
                paper.source_path = str(entry["source_path"])  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
            await db.commit()

        if (
            body.trigger_ingest
            and paper.source_path
            and paper.status in {PaperStatus.metadata_only, PaperStatus.failed}
        ):
            resp = _dispatch(paper)
            await db.commit()
        else:
            resp = IngestResponse(
                paper_id=paper.id,  # ty:ignore[invalid-argument-type]
                task_id=str(paper.celery_task_id) or "",
                status="metadata_only",  # type: ignore[arg-type]
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
    url = body.url

    # Try Zotero with the abstract page URL (e.g. arxiv abs page, not PDF)
    # Zotero returns richer metadata (year, DOI, journal) than GROBID can.
    zotero_url = _arxiv_abstract_url(url)
    meta = await fetch_metadata_from_url(zotero_url, settings.zotero_url) or {}
    meta.setdefault("url", url)

    # Use Zotero's PDF URL if provided, otherwise the normalized PDF URL
    pdf_url = meta.get("source_path") or _arxiv_pdf_url(url)
    meta["source_path"] = pdf_url

    paper = Paper(
        status=PaperStatus.metadata_only,
        **{k: v for k, v in meta.items() if hasattr(Paper, k)},
    )
    db.add(paper)
    await db.flush()

    if body.trigger_ingest:
        await db.commit()
        resp = _dispatch(paper)
        await db.commit()
    else:
        resp = IngestResponse(
            paper_id=paper.id,  # ty:ignore[invalid-argument-type]
            task_id="",
            status="metadata_only",  # type: ignore[arg-type]
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
        paper.source_path = body.source_path  # type: ignore[assignment]  # ty:ignore[invalid-assignment]

    if not paper.source_path:
        raise HTTPException(
            status_code=422,
            detail="No source_path on record — provide one in the request body",
        )

    paper.error_message = None  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
    resp = _dispatch(paper)
    await db.commit()
    return resp


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
    if had_embeddings:
        background_tasks.add_task(delete_paper_embeddings, pid)
