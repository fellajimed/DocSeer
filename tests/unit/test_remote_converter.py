from __future__ import annotations

from unittest.mock import patch

import pytest

from docseer.converters.remote import RemoteContentExtractor


def test_sends_pdf_bytes_and_returns_content():
    extractor = RemoteContentExtractor("http://localhost:8765")
    fake_bytes = b"%PDF-1.4 fake"

    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "content": "# Hello\n\nWorld."
        }

        result = extractor(doc_path="paper.pdf", doc_bytes=fake_bytes)

    assert result == {"content": "# Hello\n\nWorld."}
    mock_post.assert_called_once_with(
        "http://localhost:8765/convert",
        files={"file": ("paper.pdf", fake_bytes, "application/pdf")},
        timeout=600,
    )


def test_trailing_slash_stripped():
    extractor = RemoteContentExtractor("http://localhost:8765/")

    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"content": "ok"}

        extractor(doc_path="paper.pdf", doc_bytes=b"data")

    url_used = mock_post.call_args[0][0]
    assert url_used == "http://localhost:8765/convert"
    assert "//convert" not in url_used


def test_raises_on_http_error():
    extractor = RemoteContentExtractor("http://localhost:8765")

    with patch("requests.post") as mock_post:
        mock_post.return_value.ok = False
        mock_post.return_value.status_code = 503
        mock_post.return_value.json.return_value = {
            "error": "Service Unavailable"
        }

        with pytest.raises(
            RuntimeError, match="Remote converter returned 503"
        ):
            extractor(doc_path="paper.pdf", doc_bytes=b"data")


def test_raises_on_server_error_response():
    extractor = RemoteContentExtractor("http://localhost:8765")

    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"error": "Something broke"}

        with pytest.raises(RuntimeError, match="Remote converter error"):
            extractor(doc_path="paper.pdf", doc_bytes=b"data")


def test_custom_timeout():
    extractor = RemoteContentExtractor("http://localhost:8765", timeout=120)

    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"content": "ok"}

        extractor(doc_path="paper.pdf", doc_bytes=b"data")

    assert mock_post.call_args[1]["timeout"] == 120
