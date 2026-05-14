"""Unit tests for backend.app.services.ingest.delete_paper_embeddings."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from backend.app.services.ingest import delete_paper_embeddings


def _make_chroma_mock(raise_on_delete: Exception | None = None) -> MagicMock:
    col = MagicMock()
    if raise_on_delete:
        col.delete.side_effect = raise_on_delete
    client = MagicMock()
    client.get_or_create_collection.return_value = col
    return client, col


def _make_docstore_mock(
    is_empty: bool = False,
    raise_on_delete: Exception | None = None,
) -> MagicMock:
    ds = MagicMock()
    ds.is_empty = is_empty
    if raise_on_delete:
        ds.delete.side_effect = raise_on_delete
    return ds


# ── happy path ────────────────────────────────────────────────────────────────


async def test_delete_calls_chroma_and_docstore():
    client_mock, col_mock = _make_chroma_mock()
    ds_mock = _make_docstore_mock(is_empty=False)

    with (
        patch(
            "backend.app.services.ingest.chromadb.HttpClient",
            return_value=client_mock,
        ),
        patch(
            "backend.app.services.ingest.LocalFileStoreDB",
            return_value=ds_mock,
        ),
    ):
        await delete_paper_embeddings("paper-123")

    col_mock.delete.assert_called_once_with(where={"document_id": "paper-123"})
    ds_mock.delete.assert_called_once_with("paper-123")


# ── chroma error is swallowed ─────────────────────────────────────────────────


async def test_chroma_error_does_not_raise():
    client_mock, _ = _make_chroma_mock(
        raise_on_delete=RuntimeError("chroma down")
    )
    ds_mock = _make_docstore_mock(is_empty=False)

    with (
        patch(
            "backend.app.services.ingest.chromadb.HttpClient",
            return_value=client_mock,
        ),
        patch(
            "backend.app.services.ingest.LocalFileStoreDB",
            return_value=ds_mock,
        ),
    ):
        # should not raise
        await delete_paper_embeddings("paper-err")

    ds_mock.delete.assert_called_once()


# ── empty docstore skips delete ───────────────────────────────────────────────


async def test_empty_docstore_skips_delete():
    client_mock, _ = _make_chroma_mock()
    ds_mock = _make_docstore_mock(is_empty=True)

    with (
        patch(
            "backend.app.services.ingest.chromadb.HttpClient",
            return_value=client_mock,
        ),
        patch(
            "backend.app.services.ingest.LocalFileStoreDB",
            return_value=ds_mock,
        ),
    ):
        await delete_paper_embeddings("paper-empty")

    ds_mock.delete.assert_not_called()


# ── docstore error is swallowed ───────────────────────────────────────────────


async def test_docstore_error_does_not_raise():
    client_mock, _ = _make_chroma_mock()
    ds_mock = _make_docstore_mock(
        is_empty=False, raise_on_delete=OSError("disk full")
    )

    with (
        patch(
            "backend.app.services.ingest.chromadb.HttpClient",
            return_value=client_mock,
        ),
        patch(
            "backend.app.services.ingest.LocalFileStoreDB",
            return_value=ds_mock,
        ),
    ):
        await delete_paper_embeddings("paper-oserr")
