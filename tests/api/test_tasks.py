"""API tests for /tasks router."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _mock_result(state: str, info=None, result=None) -> MagicMock:
    r = MagicMock()
    r.state = state
    r.info = info or {}
    r.result = result
    return r


# ── state variations ──────────────────────────────────────────────────────────


async def test_task_pending(async_client):
    with patch(
        "backend.app.routers.tasks.celery_app.AsyncResult",
        return_value=_mock_result("PENDING"),
    ):
        resp = await async_client.get("/tasks/some-task-id")

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "PENDING"
    assert body["result"] is None
    assert body["error"] is None
    assert body["progress"] is None


async def test_task_started_with_progress(async_client):
    info = {"step": "embedding", "paper_id": "abc-123"}
    with patch(
        "backend.app.routers.tasks.celery_app.AsyncResult",
        return_value=_mock_result("STARTED", info=info),
    ):
        resp = await async_client.get("/tasks/some-task-id")

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "STARTED"
    assert body["progress"] == {"step": "embedding", "paper_id": "abc-123"}
    assert body["result"] is None
    assert body["error"] is None


async def test_task_success(async_client):
    task_result = {"paper_id": "abc-123", "chunk_count": 42}
    mock_r = _mock_result("SUCCESS", result=task_result)
    mock_r.result = task_result

    with patch(
        "backend.app.routers.tasks.celery_app.AsyncResult",
        return_value=mock_r,
    ):
        resp = await async_client.get("/tasks/some-task-id")

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "SUCCESS"
    assert body["result"] == task_result
    assert body["error"] is None


async def test_task_failure(async_client):
    exc = RuntimeError("Ingestion blew up")
    mock_r = _mock_result("FAILURE", result=exc)
    mock_r.result = exc

    with patch(
        "backend.app.routers.tasks.celery_app.AsyncResult",
        return_value=mock_r,
    ):
        resp = await async_client.get("/tasks/some-task-id")

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "FAILURE"
    assert "Ingestion blew up" in body["error"]
    assert body["result"] is None


async def test_task_retry(async_client):
    exc = ConnectionError("broker down")
    mock_r = _mock_result("RETRY", result=exc)
    mock_r.result = exc

    with patch(
        "backend.app.routers.tasks.celery_app.AsyncResult",
        return_value=mock_r,
    ):
        resp = await async_client.get("/tasks/some-task-id")

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "RETRY"
    assert body["error"] is not None


async def test_task_id_passed_through(async_client):
    captured = {}

    def _capture(task_id):
        captured["id"] = task_id
        return _mock_result("PENDING")

    with patch(
        "backend.app.routers.tasks.celery_app.AsyncResult",
        side_effect=_capture,
    ):
        await async_client.get("/tasks/my-specific-task-id")

    assert captured["id"] == "my-specific-task-id"
