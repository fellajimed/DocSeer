"""Unit tests for backend.app.services.metadata."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.metadata import (
    _zotero_item_to_dict,
    fetch_metadata_from_url,
    grobid_metadata_to_paper,
    parse_bibtex,
)

# ── parse_bibtex ──────────────────────────────────────────────────────────────

BIBTEX_SINGLE = """\
@article{doe2024test,
  author    = {Doe, John and Smith, Jane},
  title     = {A Test Paper},
  year      = {2024},
  journal   = {Journal of Testing},
  doi       = {10.1234/test},
  url       = {https://example.com/paper},
  abstract  = {This is the abstract.},
}
"""

BIBTEX_WITH_FILE = """\
@article{doe2024file,
  author = {Doe, John},
  title  = {Paper With File},
  year   = {2023},
  file   = {:path/to/paper.pdf:application/pdf},
}
"""

BIBTEX_NO_FILE = """\
@article{doe2024nofile,
  author = {Doe, John},
  title  = {Paper Without File},
  year   = {2022},
}
"""

BIBTEX_TWO_ENTRIES = BIBTEX_SINGLE + "\n" + BIBTEX_WITH_FILE


def test_parse_bibtex_basic():
    papers = parse_bibtex(BIBTEX_SINGLE)
    assert len(papers) == 1
    p = papers[0]
    assert p["bibtex_key"] == "doe2024test"
    assert p["title"] == "A Test Paper"
    assert p["year"] == 2024
    assert p["journal"] == "Journal of Testing"
    assert p["doi"] == "10.1234/test"
    assert p["url"] == "https://example.com/paper"
    assert p["abstract"] == "This is the abstract."


def test_parse_bibtex_author_splitting():
    papers = parse_bibtex(BIBTEX_SINGLE)
    authors = papers[0]["authors"]
    assert authors == ["John Doe", "Jane Smith"]


def test_parse_bibtex_file_path_extracted():
    papers = parse_bibtex(BIBTEX_WITH_FILE)
    assert papers[0]["source_path"] == "path/to/paper.pdf"


def test_parse_bibtex_no_file_source_path_is_none():
    papers = parse_bibtex(BIBTEX_NO_FILE)
    assert papers[0]["source_path"] is None


def test_parse_bibtex_multiple_entries():
    papers = parse_bibtex(BIBTEX_TWO_ENTRIES)
    assert len(papers) == 2
    keys = {p["bibtex_key"] for p in papers}
    assert keys == {"doe2024test", "doe2024file"}


def test_parse_bibtex_empty_string():
    papers = parse_bibtex("")
    assert papers == []


def test_parse_bibtex_bibtex_raw_present():
    papers = parse_bibtex(BIBTEX_SINGLE)
    assert papers[0]["bibtex_raw"]  # non-empty string


def test_parse_bibtex_year_none_when_missing():
    bib = "@article{k,author={A},title={T},}"
    papers = parse_bibtex(bib)
    assert papers[0]["year"] is None


# ── grobid_metadata_to_paper ──────────────────────────────────────────────────


def test_grobid_metadata_to_paper_full():
    raw = {
        "title": "GROBID Paper",
        "authors": ["Alice", "Bob"],
        "abstract": "An abstract.",
        "doi": "10.9999/grobid",
        "year": "2021",
        "journal": "Test Journal",
    }
    result = grobid_metadata_to_paper(raw)
    assert result["title"] == "GROBID Paper"
    assert result["authors"] == ["Alice", "Bob"]
    assert result["abstract"] == "An abstract."
    assert result["doi"] == "10.9999/grobid"
    assert result["year"] == 2021
    assert result["journal"] == "Test Journal"


def test_grobid_metadata_to_paper_missing_fields():
    result = grobid_metadata_to_paper({})
    assert result["title"] is None
    assert result["authors"] == []
    assert result["year"] is None
    assert result["doi"] is None


def test_grobid_metadata_to_paper_year_string():
    result = grobid_metadata_to_paper({"year": "2019-03-01"})
    assert result["year"] == 2019


# ── fetch_metadata_from_url ───────────────────────────────────────────────────


@pytest.fixture
def zotero_item():
    return {
        "title": "Fetched Paper",
        "creators": [
            {
                "creatorType": "author",
                "firstName": "Alice",
                "lastName": "Smith",
            },
        ],
        "date": "2023",
        "publicationTitle": "Science",
        "DOI": "10.0001/fetch",
        "url": "https://example.com",
        "abstractNote": "Abstract here.",
        "key": "ZKEY1",
    }


async def test_fetch_metadata_200(zotero_item):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [zotero_item]
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch(
        "backend.app.services.metadata.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await fetch_metadata_from_url(
            "https://example.com", "http://zotero"
        )

    assert result is not None
    assert result["title"] == "Fetched Paper"
    assert result["authors"] == ["Alice Smith"]
    assert result["year"] == 2023
    assert result["doi"] == "10.0001/fetch"


async def test_fetch_metadata_501_returns_none():
    mock_resp = MagicMock()
    mock_resp.status_code = 501

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch(
        "backend.app.services.metadata.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await fetch_metadata_from_url(
            "https://nope.com", "http://zotero"
        )

    assert result is None


async def test_fetch_metadata_300_picks_first(zotero_item):
    """300 Multiple Choices — server returns a map; we pick the first key."""
    resp_300 = MagicMock()
    resp_300.status_code = 300
    resp_300.json.return_value = {
        "session": "sess1",
        "items": {"KEY1": "Some Paper Title"},
    }

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = [zotero_item]
    resp_200.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=[resp_300, resp_200])

    with patch(
        "backend.app.services.metadata.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await fetch_metadata_from_url(
            "https://multi.com", "http://zotero"
        )

    assert result is not None
    assert result["title"] == "Fetched Paper"


async def test_fetch_metadata_http_error_returns_none():
    import httpx as _httpx

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=_httpx.ConnectError("refused"))

    with patch(
        "backend.app.services.metadata.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await fetch_metadata_from_url(
            "https://down.com", "http://zotero"
        )

    assert result is None


# ── _zotero_item_to_dict source_path extraction ───────────────────────────────


def test_zotero_source_path_from_attachments():
    item = {
        "title": "Test Paper",
        "creators": [],
        "date": "2024",
        "attachments": [
            {
                "url": "https://arxiv.org/pdf/2407.01985.pdf",
                "contentType": "application/pdf",
            },
            {
                "url": "https://example.com/supplemental.zip",
                "contentType": "application/zip",
            },
        ],
    }
    result = _zotero_item_to_dict(item)
    assert result["source_path"] == "https://arxiv.org/pdf/2407.01985.pdf"


def test_zotero_source_path_from_mimetype():
    item = {
        "title": "Test Paper",
        "creators": [],
        "date": "2024",
        "attachments": [
            {
                "url": "https://example.com/paper.pdf",
                "mimeType": "application/pdf",
            },
        ],
    }
    result = _zotero_item_to_dict(item)
    assert result["source_path"] == "https://example.com/paper.pdf"


def test_zotero_source_path_from_links_enclosure():
    item = {
        "title": "Test Paper",
        "creators": [],
        "date": "2024",
        "links": {
            "enclosure": {
                "href": "https://example.com/paper.pdf",
                "type": "application/pdf",
            }
        },
    }
    result = _zotero_item_to_dict(item)
    assert result["source_path"] == "https://example.com/paper.pdf"


def test_zotero_source_path_none_when_no_pdf():
    item = {
        "title": "Test Paper",
        "creators": [],
        "date": "2024",
        "attachments": [
            {
                "url": "https://example.com/page.html",
                "contentType": "text/html",
            },
        ],
    }
    result = _zotero_item_to_dict(item)
    assert result["source_path"] is None


def test_zotero_source_path_attachments_first_pdf():
    """Should pick the first PDF attachment, not a later non-PDF one."""
    item = {
        "title": "Test Paper",
        "creators": [],
        "date": "2024",
        "attachments": [
            {
                "url": "https://example.com/paper.pdf",
                "contentType": "application/pdf",
            },
            {
                "url": "https://example.com/alt.pdf",
                "contentType": "application/pdf",
            },
        ],
    }
    result = _zotero_item_to_dict(item)
    assert result["source_path"] == "https://example.com/paper.pdf"
