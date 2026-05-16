"""
Async helpers used by the FastAPI layer.
Heavy ingest work lives in backend/app/tasks/ingest.py (Celery).
"""

from __future__ import annotations

import asyncio
import logging

import chromadb

from docseer.databases import LocalFileStoreDB

from ..config import get_settings

logger = logging.getLogger(__name__)


async def delete_paper_embeddings(paper_id: str) -> None:
    """
    Remove all vectors and parent-chunk docs for *paper_id*.
    Runs in a thread-pool so it never blocks the event loop.
    Deliberately does NOT require the embeddings model — ChromaDB delete
    and LocalFileStore delete are both metadata/ID operations only.
    """
    settings = get_settings()

    def _sync() -> None:
        try:
            client = chromadb.HttpClient(
                host=settings.chroma_host, port=settings.chroma_port
            )
            col = client.get_or_create_collection("vector_db")
            col.delete(where={"document_id": paper_id})
            logger.info("Deleted ChromaDB vectors for paper %s", paper_id)
        except Exception as exc:
            logger.warning(
                "ChromaDB delete failed for paper %s: %s", paper_id, exc
            )

        try:
            docstore = LocalFileStoreDB(settings.docstore_path)
            if not docstore.is_empty:
                docstore.delete(paper_id)
                logger.info("Deleted docstore chunks for paper %s", paper_id)
        except Exception as exc:
            logger.warning(
                "Docstore delete failed for paper %s: %s", paper_id, exc
            )

    await asyncio.to_thread(_sync)
