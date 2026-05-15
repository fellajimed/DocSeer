import re
import requests


def get_file_bytes(path_or_url: str) -> bytes:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        response = requests.get(path_or_url, timeout=20)
        response.raise_for_status()
        return response.content
    else:
        with open(path_or_url, "rb") as f:
            return f.read()


def extract_metadata(url: str, doc_bytes: bytes):
    response = requests.post(url, files={"input": doc_bytes})
    return bibtex_to_dict(response.text)


def parse_authors(author_string: str) -> str:
    if not author_string:
        return ""

    authors = []
    for a in author_string.split(" and "):
        a = a.strip()

        if "," in a:
            last, first = [p.strip() for p in a.split(",", 1)]
            authors.append(f"{first} {last}")
        else:
            authors.append(a)

    return "; ".join(authors)


def bibtex_to_dict(bibtex: str) -> dict:
    bibtex = bibtex.strip()

    fields = re.findall(r"(\w+)\s*=\s*\{([^}]*)\}", bibtex)
    result = {k.lower(): v.strip() for k, v in fields}

    return {
        "title": result.get("title", "").title(),
        "author": parse_authors(result.get("author", "")),
        "abstract": result.get("abstract", ""),
    }
