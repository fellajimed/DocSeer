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
        if not response.ok:
            try:
                body = response.json()
                detail = body.get("error", str(body))
            except Exception:
                detail = response.text[:500]
            raise RuntimeError(
                f"Remote converter returned {response.status_code}: {detail}"
            )
        data: dict[str, Any] = response.json()
        if "error" in data:
            raise RuntimeError(f"Remote converter error: {data['error']}")
        return data
