import os
import re
import requests


def get_file_bytes(path_or_url: str) -> bytes:
    if os.path.isfile(path_or_url):
        with open(path_or_url, "rb") as f:
            data = f.read()
    else:
        response = requests.get(path_or_url)
        response.raise_for_status()
        data = response.content
    return data


def extract_metadata(url: str, doc_bytes: bytes):
    response = requests.post(url, files={"input": doc_bytes})
    return bibtex_to_dict(response.text)


def parse_authors(author_string: str) -> str:
    if not author_string:
        return ""

    authors = []
    # BibTeX separates authors with " and "
    for a in author_string.split(" and "):
        a = a.strip()

        if "," in a:
            # format: Last, First
            last, first = [p.strip() for p in a.split(",", 1)]
            authors.append(f"{first} {last}")
        else:
            # format: First Last
            authors.append(a)

    return "; ".join(authors)


def bibtex_to_dict(bibtex: str) -> dict:
    bibtex = bibtex.strip()

    # Extract fields
    fields = re.findall(r"(\w+)\s*=\s*\{([^}]*)\}", bibtex)
    result = {k.lower(): v.strip() for k, v in fields}

    return {
        "title": result.get("title", "").title(),
        "author": parse_authors(result.get("author", "")),
        "abstract": result.get("abstract", ""),
    }
