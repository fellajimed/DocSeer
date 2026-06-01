from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class RemoteContentExtractor:
    """Content extractor that delegates PDF→Markdown conversion to a remote
    Docling server running on the host (with Metal GPU acceleration)."""

    def __init__(self, url: str, timeout: int = 600):
        self.url = url.rstrip("/") + "/convert"
        self.timeout = timeout

    def __call__(
        self, *, doc_path: str, doc_bytes: bytes, **kwargs: Any
    ) -> dict[str, Any]:
        response = requests.post(
            self.url,
            files={"file": (doc_path, doc_bytes, "application/pdf")},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        if "error" in data:
            raise RuntimeError(
                f"Remote converter error: {data['error']}"
            )
        return data
