from textwrap import dedent
from langchain_core.documents import Document


def docs_to_md(docs: list[Document]) -> str:
    return "\n----------\n".join(map(doc_to_md, docs))


def doc_to_md(doc: Document) -> str:
    return dedent(f"""
        * Title: {doc.metadata.get("title", "Not provided")}
        * Authors: {doc.metadata.get("author", "Not provided")}
        * Abstract: {doc.metadata.get("abstract", "Not provided")}
        * Content: {doc.page_content}
    """)
