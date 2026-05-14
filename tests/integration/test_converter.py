"""
Integration test: real Docling conversion on the fixture PDF.

Marked @pytest.mark.slow — skipped in fast CI runs.
Run explicitly with:  pytest -m slow
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURE_PDF = Path(__file__).parent.parent / "fixtures" / "2407.12211.pdf"

pytestmark = pytest.mark.slow


@pytest.mark.skipif(
    not FIXTURE_PDF.exists(),
    reason="Fixture PDF not found",
)
def test_content_extractor_on_real_pdf():
    """ContentExtractor returns non-empty markdown starting with the paper title."""
    from docseer.converters.content_extractor import ContentExtractor

    extractor = ContentExtractor()
    result = extractor(
        doc_path=str(FIXTURE_PDF), doc_bytes=FIXTURE_PDF.read_bytes()
    )

    content = result.get("content", "")
    assert isinstance(content, str)
    assert len(content) > 1000, "Expected substantial markdown output"
    # The paper title should appear near the top
    assert "Calibration" in content[:500] or "Epistemic" in content[:1000]


@pytest.mark.skipif(
    not FIXTURE_PDF.exists(),
    reason="Fixture PDF not found",
)
def test_doc_converter_grobid_failure_still_returns_content():
    """
    DocConverter.convert() should return content even when GROBID is
    unreachable (metadata extraction failure is caught and logged).
    """
    from docseer.converters.converter import DocConverter

    # Force MetadataExtractor to raise so we exercise the fallback path
    with patch(
        "docseer.converters.converter.MetadataExtractor.__call__",
        side_effect=ConnectionError("GROBID unreachable"),
    ):
        converter = DocConverter(
            url="http://localhost:9999/api/processHeaderDocument"
        )
        result = converter.convert(str(FIXTURE_PDF))

    assert "content" in result
    assert len(result["content"]) > 1000


@pytest.mark.skipif(
    not FIXTURE_PDF.exists(),
    reason="Fixture PDF not found",
)
def test_chunker_on_real_pdf_content():
    """ParentChildChunker produces valid parent/child structure on real content."""
    from docseer.converters.content_extractor import ContentExtractor
    from docseer.chunkers.parent_child_chunker import ParentChildChunker

    extractor = ContentExtractor()
    result = extractor(
        doc_path=str(FIXTURE_PDF), doc_bytes=FIXTURE_PDF.read_bytes()
    )
    content = result["content"]

    chunker = ParentChildChunker()
    chunks = chunker.chunk(content, "2407.12211")

    assert len(chunks["parent_ids"]) >= 1
    assert len(chunks["chunks"]) >= len(chunks["parent_ids"])

    for child in chunks["chunks"]:
        assert child.metadata["document_id"] == "2407.12211"
        assert child.metadata["parent_id"] in chunks["parent_ids"]
