from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from docseer.converters.server import app


def test_health_returns_ok():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_convert_returns_content(monkeypatch):
    mock_extractor = MagicMock()
    mock_extractor.return_value = {"content": "# Hello\n\nWorld."}
    monkeypatch.setattr(
        "docseer.converters.server._get_extractor",
        lambda: mock_extractor,
    )

    client = TestClient(app)
    resp = client.post(
        "/convert",
        files={"file": ("test.pdf", b"%PDF-1.4 fake content", "application/pdf")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"content": "# Hello\n\nWorld."}
    mock_extractor.assert_called_once()


def test_convert_empty_file_returns_400():
    client = TestClient(app)
    resp = client.post(
        "/convert",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "Empty file"}


def test_convert_extractor_error_returns_500(monkeypatch):
    mock_extractor = MagicMock()
    mock_extractor.side_effect = RuntimeError("Docling crashed")
    monkeypatch.setattr(
        "docseer.converters.server._get_extractor",
        lambda: mock_extractor,
    )

    client = TestClient(app)
    resp = client.post(
        "/convert",
        files={"file": ("bad.pdf", b"garbage", "application/pdf")},
    )
    assert resp.status_code == 500
    assert "Docling crashed" in resp.json()["error"]
