from .utils import extract_metadata


GROBID_URL = "http://localhost:8070/api/processHeaderDocument"


class MetadataExtractor:
    def __init__(self, url: str | None = None):
        self.url = url or GROBID_URL

    def __call__(self, *, doc_bytes: bytes, **kwargs) -> dict:
        return extract_metadata(self.url, doc_bytes)
