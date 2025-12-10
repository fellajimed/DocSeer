import asyncio
from .utils import get_file_bytes
from .content_extractor import ContentExtractor
from .metadata_extractor import MetadataExtractor


class DocConverter:
    """
    PDF to Markdown Converter + metadata
    """

    def __init__(self, url: str | None = None):
        self._content_extractor = ContentExtractor()
        self._metadata_extractor = MetadataExtractor(url=url)

    def convert(self, doc_path: str) -> dict:
        doc_bytes = get_file_bytes(doc_path)

        metadata = self._metadata_extractor(doc_bytes=doc_bytes)
        content = self._content_extractor(
            doc_path=doc_path, doc_bytes=doc_bytes
        )

        return metadata | content

    async def aconvert(self, doc_path: str) -> dict:
        doc_bytes = await asyncio.to_thread(get_file_bytes, doc_path)

        metadata_task = asyncio.to_thread(
            self._metadata_extractor, doc_bytes=doc_bytes
        )
        content_task = asyncio.to_thread(
            self._content_extractor, doc_path=doc_path, doc_bytes=doc_bytes
        )

        metadata, content = await asyncio.gather(metadata_task, content_task)

        return metadata | content


if __name__ == "__main__":
    doc_converter = DocConverter()

    print(doc_converter("https://arxiv.org/pdf/2407.01985"))
    print("-" * 150)
    print(
        doc_converter.convert(
            "/Users/mohammed/Zotero/storage/4MRHHSWG/He_et_al._"
            "-_2015_-_Deep_Residual_Learning_for_Image_Recognition.pdf"
        )
    )
