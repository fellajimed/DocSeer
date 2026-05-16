"""Unit tests for docseer.chunkers.parent_child_chunker."""

from __future__ import annotations

from docseer.chunkers.parent_child_chunker import ParentChildChunker

SAMPLE_MD = """\
# Introduction

This section introduces the topic in detail with enough words to ensure
child chunking actually splits things when the chunk size is small.

## Background

Here we discuss the background of the problem and related work.
This is a second paragraph in the background section.

## Method

Our method consists of several steps. First we do X. Then we do Y.
Finally we evaluate on benchmark Z.

# Conclusion

We conclude that the approach works well.
"""


def _chunker(child_chunk_size: int = 200) -> ParentChildChunker:
    return ParentChildChunker(
        child_chunk_size=child_chunk_size, child_chunk_overlap=20
    )


# ── basic structure ───────────────────────────────────────────────────────────


def test_chunk_returns_all_keys():
    result = _chunker().chunk(SAMPLE_MD, "doc-1")
    assert set(result.keys()) == {"chunks", "parent_ids", "parent_chunks"}


def test_parent_ids_format():
    result = _chunker().chunk(SAMPLE_MD, "doc-1")
    for i, pid in enumerate(result["parent_ids"]):
        assert pid == f"doc-1-{i}"


def test_child_ids_format():
    result = _chunker().chunk(SAMPLE_MD, "doc-1")
    for child in result["chunks"]:
        # id format: doc-1-{parent_idx}-{child_idx}
        parts = child.id.split("-")
        assert parts[0] == "doc"
        assert parts[1] == "1"
        assert len(parts) >= 4


def test_child_metadata_keys():
    result = _chunker().chunk(SAMPLE_MD, "doc-1")
    for child in result["chunks"]:
        assert "parent_id" in child.metadata
        assert "document_id" in child.metadata


def test_document_id_propagated():
    result = _chunker().chunk(SAMPLE_MD, "my-doc")
    for child in result["chunks"]:
        assert child.metadata["document_id"] == "my-doc"


def test_child_parent_id_matches_parent():
    result = _chunker().chunk(SAMPLE_MD, "doc-1")
    parent_ids = set(result["parent_ids"])
    for child in result["chunks"]:
        assert child.metadata["parent_id"] in parent_ids


def test_at_least_one_parent_and_child():
    result = _chunker().chunk(SAMPLE_MD, "doc-1")
    assert len(result["parent_ids"]) >= 1
    assert len(result["chunks"]) >= 1


def test_parent_count_equals_parent_ids_count():
    result = _chunker().chunk(SAMPLE_MD, "doc-1")
    assert len(result["parent_ids"]) == len(result["parent_chunks"])


def test_child_content_nonempty():
    result = _chunker().chunk(SAMPLE_MD, "doc-1")
    for child in result["chunks"]:
        assert child.page_content.strip()


# ── small chunk size forces splitting ─────────────────────────────────────────


def test_small_chunk_size_produces_multiple_children():
    # With chunk_size=100 each parent section should split into >1 child
    result = ParentChildChunker(
        child_chunk_size=100, child_chunk_overlap=10
    ).chunk(SAMPLE_MD, "doc-small")
    assert len(result["chunks"]) > len(result["parent_ids"])


# ── async wrapper ─────────────────────────────────────────────────────────────


async def test_achunk_matches_sync():
    c = _chunker()
    sync_result = c.chunk(SAMPLE_MD, "doc-async")
    async_result = await c.achunk(SAMPLE_MD, "doc-async")

    assert len(async_result["parent_ids"]) == len(sync_result["parent_ids"])
    assert len(async_result["chunks"]) == len(sync_result["chunks"])


# ── edge cases ────────────────────────────────────────────────────────────────


def test_single_paragraph_no_headers():
    md = "Just a single paragraph with no markdown headers at all."
    result = _chunker().chunk(md, "plain")
    assert len(result["parent_ids"]) == 1
    assert len(result["chunks"]) >= 1


def test_different_doc_ids_are_isolated():
    c = _chunker()
    r1 = c.chunk(SAMPLE_MD, "doc-A")
    r2 = c.chunk(SAMPLE_MD, "doc-B")
    ids_a = {ch.id for ch in r1["chunks"]}
    ids_b = {ch.id for ch in r2["chunks"]}
    assert ids_a.isdisjoint(ids_b)
