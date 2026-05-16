"""
Metadata helpers:
  - parse_bibtex()          — parse a Zotero BibTeX export string
  - fetch_metadata_from_url() — call Zotero Translation Server for a URL
  - grobid_metadata_to_paper() — normalise GROBID output to our schema dict
"""

from __future__ import annotations

import logging
from typing import Any

import bibtexparser
import httpx

logger = logging.getLogger(__name__)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip().strip("{}").strip()
    return s or None


def _parse_year(value: Any) -> int | None:
    try:
        return int(str(value).strip()[:4])
    except (TypeError, ValueError):
        return None


def _split_authors(raw: str | None) -> list[str]:
    """BibTeX 'author' field: comma-separated last, first joined by ' and '."""
    if not raw:
        return []
    authors = []
    for part in raw.split(" and "):
        part = part.strip().strip("{}")
        if "," in part:
            last, first = part.split(",", 1)
            authors.append(f"{first.strip()} {last.strip()}")
        else:
            authors.append(part)
    return [a for a in authors if a]


def _entry_to_raw(entry) -> str:
    lib = bibtexparser.Library()
    lib.add(entry)
    return bibtexparser.write_string(lib)


def parse_bibtex(bibtex_str: str) -> list[dict[str, Any]]:
    """
    Parse a BibTeX string exported from Zotero into a list of paper dicts
    compatible with PaperCreate / Paper model fields.
    """
    library = bibtexparser.parse_string(bibtex_str)
    papers: list[dict[str, Any]] = []

    for entry in library.entries:
        fields: dict[str, Any] = {f.key: f.value for f in entry.fields}

        raw_file: str = str(fields.get("file", "") or "")
        source_path: str | None = None
        if raw_file:
            parts = raw_file.split(":")
            if len(parts) >= 2:
                candidate = parts[1].strip()
                source_path = candidate or None
            else:
                source_path = _clean(raw_file)

        if not source_path:
            source_path = _clean(fields.get("url"))

        paper: dict[str, Any] = {
            "bibtex_key": entry.key,
            "bibtex_raw": _entry_to_raw(entry),
            "title": _clean(fields.get("title")),
            "authors": _split_authors(str(fields.get("author", "") or "")),
            "year": _parse_year(fields.get("year")),
            "journal": _clean(
                fields.get("journal") or fields.get("booktitle")
            ),
            "publisher": _clean(fields.get("publisher")),
            "doi": _clean(fields.get("doi")),
            "url": _clean(fields.get("url")),
            "isbn": _clean(fields.get("isbn")),
            "abstract": _clean(fields.get("abstract")),
            "source_path": source_path,
            "extra_metadata": {
                k: str(v)
                for k, v in fields.items()
                if k
                not in {
                    "author",
                    "title",
                    "year",
                    "journal",
                    "booktitle",
                    "publisher",
                    "doi",
                    "url",
                    "isbn",
                    "abstract",
                    "file",
                }
            },
        }
        papers.append(paper)

    return papers


def _zotero_item_to_dict(item: dict[str, Any]) -> dict[str, Any]:
    creators = item.get("creators", [])
    authors = [
        f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
        for c in creators
        if c.get("creatorType") == "author"
    ]

    year: int | None = None
    date_str: str = str(item.get("date", "") or "")
    if date_str:
        year = _parse_year(date_str)

    source_path = None
    for att in item.get("attachments") or []:
        url = att.get("url")
        ctype = (att.get("contentType") or att.get("mimeType") or "").lower()
        if url and "pdf" in ctype:
            source_path = url
            break
    if not source_path:
        enclosure = (item.get("links") or {}).get("enclosure") or {}
        if enclosure.get("type") == "application/pdf":
            source_path = enclosure.get("href")

    return {
        "title": item.get("title"),
        "authors": authors,
        "year": year,
        "journal": item.get("publicationTitle") or item.get("bookTitle"),
        "publisher": item.get("publisher"),
        "doi": item.get("DOI"),
        "url": item.get("url"),
        "source_path": source_path,
        "abstract": item.get("abstractNote"),
        "zotero_key": item.get("key"),
        "extra_metadata": {
            k: v
            for k, v in item.items()
            if k
            not in {
                "title",
                "creators",
                "date",
                "publicationTitle",
                "bookTitle",
                "publisher",
                "DOI",
                "url",
                "abstractNote",
                "key",
            }
        },
    }


async def fetch_metadata_from_url(
    url: str, zotero_base_url: str
) -> dict[str, Any] | None:
    """
    POST the URL to the Zotero Translation Server and return a normalised
    metadata dict, or None if no translator could handle the URL.

    Translation-server response codes:
      200 – array of Zotero items  (success)
      300 – multiple choices       (pick first automatically)
      501 – no translator found    (return None)
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{zotero_base_url}/web",
                content=url,
                headers={"Content-Type": "text/plain"},
            )

            if resp.status_code == 501:
                logger.info("Zotero: no translator found for %s", url)
                return None

            if resp.status_code == 300:
                payload = resp.json()
                items_map: dict = (
                    payload.get("items", {})
                    if isinstance(payload, dict)
                    else {}
                )
                if not items_map:
                    return None
                first_key = next(iter(items_map))
                session = payload.get("session", "")
                resp = await client.post(
                    f"{zotero_base_url}/web",
                    json={
                        "url": url,
                        "session": session,
                        "items": {first_key: items_map[first_key]},
                    },
                )

            resp.raise_for_status()
            items: list = resp.json()
            if not items:
                return None
            return _zotero_item_to_dict(items[0])

        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Zotero request failed for %s: %s", url, exc)
            return None


def grobid_metadata_to_paper(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Normalise the flat dict returned by GROBID / MetadataExtractor into the
    subset of fields we store on the Paper model.
    """
    authors = raw.get("authors") or raw.get("author")
    if isinstance(authors, str):
        authors = _split_authors(authors)
    return {
        "title": _clean(raw.get("title")),
        "authors": authors or [],
        "abstract": _clean(raw.get("abstract")),
        "doi": _clean(raw.get("doi")),
        "year": _parse_year(raw.get("year")),
        "journal": _clean(raw.get("journal")),
    }
