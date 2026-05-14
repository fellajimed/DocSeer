"""API tests for /papers router."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch


from backend.app.models.paper import PaperStatus
from tests.conftest import MockResult, make_paper

FAKE_TASK_ID = "celery-task-abc"


def _mock_task() -> MagicMock:
    t = MagicMock()
    t.id = FAKE_TASK_ID
    return t


# ── GET /papers/ ──────────────────────────────────────────────────────────────


async def test_list_papers_empty(async_client, mock_session):
    resp = await async_client.get("/papers/")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_papers_returns_papers(async_client, mock_session):
    paper = make_paper(title="My Paper")
    mock_session.set_default_result(MockResult([paper]))

    resp = await async_client.get("/papers/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "My Paper"


# ── GET /papers/{id} ──────────────────────────────────────────────────────────


async def test_get_paper_found(async_client, mock_session):
    paper = make_paper(title="Found Paper")
    mock_session._store[paper.id] = paper

    resp = await async_client.get(f"/papers/{paper.id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Found Paper"


async def test_get_paper_not_found(async_client):
    resp = await async_client.get(f"/papers/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── POST /papers/ ─────────────────────────────────────────────────────────────


async def test_add_paper_metadata_only(async_client):
    """No source_path → status metadata_only, no Celery task."""
    resp = await async_client.post("/papers/", json={"title": "New Paper"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "metadata_only"
    assert body["task_id"] == ""


async def test_add_paper_with_source_path_queues_ingest(async_client):
    with patch(
        "backend.app.routers.papers.ingest_paper.apply_async",
        return_value=_mock_task(),
    ):
        resp = await async_client.post(
            "/papers/",
            json={"title": "Ingest Me", "source_path": "/data/paper.pdf"},
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["task_id"] == FAKE_TASK_ID


# ── POST /papers/import-bibtex ────────────────────────────────────────────────


SAMPLE_BIBTEX = """\
@article{doe2024,
  author  = {Doe, John},
  title   = {BibTeX Paper},
  year    = {2024},
  journal = {Test Journal},
}
"""


async def test_import_bibtex_creates_paper(async_client, mock_session):
    # execute() returns None → no duplicate found
    resp = await async_client.post(
        "/papers/import-bibtex",
        json={"bibtex": SAMPLE_BIBTEX, "trigger_ingest": False},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert len(body) == 1
    assert body[0]["status"] == "metadata_only"


async def test_import_bibtex_dedup_skips_existing(async_client, mock_session):
    existing = make_paper(bibtex_key="doe2024")
    # First execute() for dedup check returns the existing paper
    mock_session.push_result(MockResult([existing]))

    resp = await async_client.post(
        "/papers/import-bibtex",
        json={"bibtex": SAMPLE_BIBTEX, "trigger_ingest": False},
    )
    assert resp.status_code == 202
    assert resp.json() == []  # skipped


async def test_import_bibtex_trigger_ingest(async_client, mock_session):
    bibtex_with_file = """\
@article{file2024,
  author = {A, B},
  title  = {Has File},
  year   = {2024},
  file   = {:path/to/paper.pdf:application/pdf},
}
"""
    with patch(
        "backend.app.routers.papers.ingest_paper.apply_async",
        return_value=_mock_task(),
    ):
        resp = await async_client.post(
            "/papers/import-bibtex",
            json={"bibtex": bibtex_with_file, "trigger_ingest": True},
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body[0]["status"] == "queued"
    assert body[0]["task_id"] == FAKE_TASK_ID


# ── POST /papers/{id}/ingest ──────────────────────────────────────────────────


async def test_trigger_ingest_queues_task(async_client, mock_session):
    paper = make_paper(source_path="/data/paper.pdf", status=PaperStatus.done)
    mock_session._store[paper.id] = paper

    with patch(
        "backend.app.routers.papers.ingest_paper.apply_async",
        return_value=_mock_task(),
    ):
        resp = await async_client.post(f"/papers/{paper.id}/ingest", json={})

    assert resp.status_code == 202
    assert resp.json()["task_id"] == FAKE_TASK_ID


async def test_trigger_ingest_409_if_processing(async_client, mock_session):
    paper = make_paper(
        source_path="/data/paper.pdf", status=PaperStatus.processing
    )
    mock_session._store[paper.id] = paper

    resp = await async_client.post(f"/papers/{paper.id}/ingest", json={})
    assert resp.status_code == 409


async def test_trigger_ingest_422_if_no_source_path(
    async_client, mock_session
):
    paper = make_paper(source_path=None, status=PaperStatus.metadata_only)
    mock_session._store[paper.id] = paper

    resp = await async_client.post(f"/papers/{paper.id}/ingest", json={})
    assert resp.status_code == 422


async def test_trigger_ingest_uses_body_source_path(
    async_client, mock_session
):
    paper = make_paper(source_path=None, status=PaperStatus.failed)
    mock_session._store[paper.id] = paper

    with patch(
        "backend.app.routers.papers.ingest_paper.apply_async",
        return_value=_mock_task(),
    ):
        resp = await async_client.post(
            f"/papers/{paper.id}/ingest",
            json={"source_path": "/data/new.pdf"},
        )
    assert resp.status_code == 202


# ── PUT /papers/{id} ──────────────────────────────────────────────────────────


async def test_update_paper(async_client, mock_session):
    paper = make_paper(title="Old Title")
    mock_session._store[paper.id] = paper

    resp = await async_client.put(
        f"/papers/{paper.id}", json={"title": "New Title"}
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "New Title"


async def test_update_paper_not_found(async_client):
    resp = await async_client.put(
        f"/papers/{uuid.uuid4()}", json={"title": "X"}
    )
    assert resp.status_code == 404


# ── DELETE /papers/{id} ───────────────────────────────────────────────────────


async def test_delete_paper_no_embeddings(async_client, mock_session):
    paper = make_paper(status=PaperStatus.metadata_only)
    mock_session._store[paper.id] = paper

    resp = await async_client.delete(f"/papers/{paper.id}")
    assert resp.status_code == 204
    assert paper.id not in mock_session._store


async def test_delete_paper_with_embeddings_queues_cleanup(
    async_client, mock_session
):
    paper = make_paper(status=PaperStatus.done)
    mock_session._store[paper.id] = paper

    with patch(
        "backend.app.routers.papers.delete_paper_embeddings"
    ) as mock_del:
        resp = await async_client.delete(f"/papers/{paper.id}")

    assert resp.status_code == 204
    mock_del.assert_called_once_with(str(paper.id))


async def test_delete_paper_not_found(async_client):
    resp = await async_client.delete(f"/papers/{uuid.uuid4()}")
    assert resp.status_code == 404
