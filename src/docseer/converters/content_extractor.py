import warnings
from io import BytesIO
from docling.datamodel.base_models import DocumentStream
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption


class ContentExtractor:
    def __init__(self, do_ocr: bool = False):
        pipeline_options = PdfPipelineOptions()
        # OCR: off by default — native digital PDFs have selectable text.
        # Pass do_ocr=True for scanned documents.
        pipeline_options.do_ocr = do_ocr
        # code detection
        pipeline_options.do_code_enrichment = True
        # formulas detection
        pipeline_options.do_formula_enrichment = False

        # Docling ≥2.x deprecated `generate_table_images` in favour of
        # `generate_page_images` + `TableItem.get_image()`.  The field is still
        # accessed internally by the pipeline, so we suppress the noise here.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Field `generate_table_images` is deprecated",
                category=DeprecationWarning,
            )
            self.converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_options
                    )
                }
            )

    def convert_pdf_bytes(self, doc_path: str, doc_bytes: bytes) -> str:
        doc_stream = DocumentStream(name=doc_path, stream=BytesIO(doc_bytes))
        return self.converter.convert(doc_stream).document.export_to_markdown()

    def __call__(self, *, doc_path: str, doc_bytes: bytes, **kwargs) -> dict:
        text_md = self.convert_pdf_bytes(doc_path, doc_bytes)
        return {"content": text_md}
