from __future__ import annotations

import argparse
import logging
import os
from functools import lru_cache

# MPS doesn't support float64 ops used by docling's layout models (transformers).
# Disable MPS detection so docling falls back to CPU, avoiding:
#   "Cannot convert a MPS Tensor to float64 dtype"
# CUDA is unaffected — it works fine with float64.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
import torch  # noqa: E402

if torch.backends.mps.is_available():

    @lru_cache(maxsize=None)
    def _mps_unavailable() -> bool:
        return False

    torch.backends.mps.is_available = _mps_unavailable
    setattr(torch.backends.mps, "is_built", lambda: False)

import uvicorn  # noqa: E402
from fastapi import FastAPI, UploadFile, File  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from .content_extractor import ContentExtractor  # noqa: E402

logger = logging.getLogger(__name__)
app = FastAPI(title="DocSeer Docling Server")
_extractor: ContentExtractor | None = None


def _get_extractor() -> ContentExtractor:
    global _extractor
    if _extractor is None:
        logger.info(
            "Initializing Docling ContentExtractor (this may take a moment)..."
        )
        _extractor = ContentExtractor()
        logger.info("Docling ContentExtractor ready.")
    return _extractor


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    doc_bytes = await file.read()
    if not doc_bytes:
        return JSONResponse(status_code=400, content={"error": "Empty file"})
    doc_path = file.filename or "document.pdf"
    try:
        extractor = _get_extractor()
        result = extractor(doc_path=doc_path, doc_bytes=doc_bytes)
        return result
    except Exception as exc:
        logger.exception("Conversion failed")
        return JSONResponse(
            status_code=500,
            content={"error": str(exc)},
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DocSeer Docling conversion server (host-side, Metal GPU)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to listen on (default: 8765)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging level (default: info)",
    )
    args = parser.parse_args()
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
