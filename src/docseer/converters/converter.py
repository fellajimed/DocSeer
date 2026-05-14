import asyncio
import logging

from .utils import get_file_bytes
from .content_extractor import ContentExtractor
from .metadata_extractor import MetadataExtractor

logger = logging.getLogger(__name__)


class DocConverter:
    """PDF → Markdown + metadata (GROBID for metadata, Docling for content)."""

    def __init__(self, url: str | None = None):
        self._content_extractor = ContentExtractor()
        self._metadata_extractor = MetadataExtractor(url=url)

    def convert(self, doc_path: str) -> dict:
        doc_bytes = get_file_bytes(doc_path)

        try:
            metadata = self._metadata_extractor(doc_bytes=doc_bytes)
        except Exception as exc:
            logger.warning("GROBID metadata extraction failed: %s", exc)
            metadata = {}

        content = self._content_extractor(
            doc_path=doc_path, doc_bytes=doc_bytes
        )
        return metadata | content

    async def aconvert(self, doc_path: str) -> dict:
        doc_bytes = await asyncio.to_thread(get_file_bytes, doc_path)

        async def _safe_metadata() -> dict:
            try:
                return await asyncio.to_thread(
                    self._metadata_extractor, doc_bytes=doc_bytes
                )
            except Exception as exc:
                logger.warning("GROBID metadata extraction failed: %s", exc)
                return {}

        metadata, content = await asyncio.gather(
            _safe_metadata(),
            asyncio.to_thread(
                self._content_extractor, doc_path=doc_path, doc_bytes=doc_bytes
            ),
        )
        return metadata | content
