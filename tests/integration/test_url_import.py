"""
Integration tests that require the running DocSeer API.

Marked @pytest.mark.requires_app — skipped unless the app is reachable.
Run with:  pytest -m requires_app
"""

from __future__ import annotations

import pytest
import requests

BASE_URL = "http://localhost:8000"

pytestmark = pytest.mark.requires_app


@pytest.fixture(scope="module")
def app_available():
    """Skip entire module if the API is not running."""
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code != 200:
            pytest.skip("API not running")
    except requests.ConnectionError:
        pytest.skip("API not running")


def _cleanup_paper(paper_id: str) -> None:
    try:
        requests.delete(f"{BASE_URL}/papers/{paper_id}", timeout=5)
    except requests.RequestException:
        pass


def _cleanup_existing(url: str) -> None:
    """Delete any paper with the given source_path to avoid duplicate key errors."""
    try:
        resp = requests.get(f"{BASE_URL}/papers/", timeout=10)
        if resp.status_code == 200:
            for p in resp.json():
                if p.get("source_path") == url:
                    _cleanup_paper(p["id"])
    except requests.RequestException:
        pass


# ── POST /papers/import-url with real arxiv PDF ──────────────────────────────


def test_import_arxiv_pdf_url(app_available):
    """
    Import the test paper via its arxiv PDF URL.
    Zotero resolves the abstract page and returns full metadata.
    """
    url = "https://arxiv.org/pdf/2407.01985"
    _cleanup_existing(url)
    resp = requests.post(
        f"{BASE_URL}/papers/import-url",
        json={"url": url, "trigger_ingest": False},
        timeout=30,
    )
    assert resp.status_code == 202
    body = resp.json()
    paper_id = body["paper_id"]

    try:
        # Fetch the paper to verify metadata
        resp = requests.get(f"{BASE_URL}/papers/{paper_id}", timeout=10)
        assert resp.status_code == 200
        data = resp.json()

        assert data["title"] == (
            "The Epistemic Uncertainty Hole: an issue of Bayesian Neural Networks"
        )
        assert "Mohammed Fellaji" in data["authors"]
        assert "Frédéric Pennerath" in data["authors"]
        assert data["year"] == 2024
        assert data["source_path"] == url
        assert "arxiv.org/abs/" in data["url"]
    finally:
        _cleanup_paper(paper_id)


def test_import_arxiv_pdf_url_with_ingest(app_available):
    """
    Import the test paper and queue ingestion.
    Verifies the full pipeline: Zotero metadata + GROBID content extraction.
    """
    url = "https://arxiv.org/pdf/2407.01985"
    _cleanup_existing(url)
    resp = requests.post(
        f"{BASE_URL}/papers/import-url",
        json={"url": url, "trigger_ingest": True},
        timeout=30,
    )
    assert resp.status_code == 202
    body = resp.json()
    paper_id = body["paper_id"]
    assert body["status"] == "queued"
    assert body["task_id"]

    try:
        # Verify initial metadata is correct
        resp = requests.get(f"{BASE_URL}/papers/{paper_id}", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == (
            "The Epistemic Uncertainty Hole: an issue of Bayesian Neural Networks"
        )
        assert data["year"] == 2024
    finally:
        _cleanup_paper(paper_id)


def test_import_url_non_arxiv_fallback(app_available):
    """
    Import a non-arxiv URL — Zotero may or may not resolve it,
    but the endpoint should still return 202.
    """
    resp = requests.post(
        f"{BASE_URL}/papers/import-url",
        json={"url": "https://example.com/paper", "trigger_ingest": False},
        timeout=30,
    )
    assert resp.status_code == 202
    body = resp.json()
    paper_id = body["paper_id"]

    try:
        resp = requests.get(f"{BASE_URL}/papers/{paper_id}", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_path"] == "https://example.com/paper"
    finally:
        _cleanup_paper(paper_id)


# ── GROBID bibtex_to_dict via real conversion ────────────────────────────────


def test_grobid_bibtex_extraction_preserves_casing(app_available):
    """
    GROBID returns BibTeX for a PDF. The bibtex_to_dict parser
    must preserve the original title casing (no .title() mangling).
    """
    from docseer.converters.utils import bibtex_to_dict

    # Simulate what GROBID actually returns for the test paper
    grobid_response = """\
@misc{-1,
  author = {Fellaji, M and Pennerath, F},
  title = {The Epistemic Uncertainty Hole: an issue of Bayesian Neural Networks},
  abstract = {Bayesian Deep Learning (BDL) gives access not only to aleatoric uncertainty.},
}
"""
    result = bibtex_to_dict(grobid_response)

    # Critical: "an issue" must NOT become "An Issue"
    assert result["title"] == (
        "The Epistemic Uncertainty Hole: an issue of Bayesian Neural Networks"
    )
    assert result["author"] == "M Fellaji; F Pennerath"
    assert "Bayesian Deep Learning" in result["abstract"]
