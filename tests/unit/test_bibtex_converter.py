"""Unit tests for src/docseer/converters/utils.py (bibtex_to_dict, parse_authors)."""

from __future__ import annotations

from docseer.converters.utils import bibtex_to_dict, parse_authors

# ── GROBID-style BibTeX (what the worker actually receives) ───────────────────

GROBID_BIBTEX = """\
@misc{-1,
  author = {Fellaji, M and Pennerath, F},
  title = {The Epistemic Uncertainty Hole: an issue of Bayesian Neural Networks},
  abstract = {Bayesian Deep Learning (BDL) gives access not only to aleatoric uncertainty.},
  keywords = {Bayesian Deep Learning, epistemic uncertainty, calibration}
}
"""

GROBID_BIBTEX_WITH_YEAR = """\
@misc{-1,
  author = {Doe, John and Smith, Jane},
  title = {A Paper With Year},
  year = {2024},
  abstract = {Abstract text.}
}
"""

# ── Arxiv-exported BibTeX (user-provided) ─────────────────────────────────────

ARXIV_BIBTEX = """\
@misc{fellaji2024epistemicuncertaintyholeissue,
      title={The Epistemic Uncertainty Hole: an issue of Bayesian Neural Networks},
      author={Mohammed Fellaji and Frédéric Pennerath},
      year={2024},
      eprint={2407.01985},
      archivePrefix={arXiv},
      primaryClass={stat.ML},
      url={https://arxiv.org/abs/2407.01985},
}
"""


def test_bibtex_to_dict_preserves_title_casing():
    """Title must NOT be mangled by .title() — "an issue" stays lowercase."""
    result = bibtex_to_dict(GROBID_BIBTEX)
    assert result["title"] == (
        "The Epistemic Uncertainty Hole: an issue of Bayesian Neural Networks"
    )


def test_bibtex_to_dict_parses_authors():
    result = bibtex_to_dict(GROBID_BIBTEX)
    assert result["author"] == "M Fellaji; F Pennerath"


def test_bibtex_to_dict_extracts_abstract():
    result = bibtex_to_dict(GROBID_BIBTEX)
    assert "Bayesian Deep Learning" in result["abstract"]


def test_bibtex_to_dict_extracts_year():
    result = bibtex_to_dict(GROBID_BIBTEX_WITH_YEAR)
    assert result["year"] == 2024


def test_bibtex_to_dict_year_none_when_missing():
    result = bibtex_to_dict(GROBID_BIBTEX)
    assert result["year"] is None


def test_bibtex_to_dict_arxiv_export():
    """Parse the full arxiv-exported BibTeX for the test paper."""
    result = bibtex_to_dict(ARXIV_BIBTEX)
    assert result["title"] == (
        "The Epistemic Uncertainty Hole: an issue of Bayesian Neural Networks"
    )
    assert result["author"] == "Mohammed Fellaji; Frédéric Pennerath"
    assert result["year"] == 2024


def test_bibtex_to_dict_empty_input():
    result = bibtex_to_dict("")
    assert result["title"] is None
    assert result["author"] == ""
    assert result["abstract"] == ""
    assert result["year"] is None


def test_bibtex_to_dict_title_with_special_chars():
    """Title containing colons, hyphens, parentheses should be preserved."""
    bib = "@misc{k,title={Deep Learning: A Survey (2020-2024)},author={A, B},}"
    result = bibtex_to_dict(bib)
    assert result["title"] == "Deep Learning: A Survey (2020-2024)"


# ── parse_authors ─────────────────────────────────────────────────────────────


def test_parse_authors_last_first():
    assert (
        parse_authors("Fellaji, M and Pennerath, F")
        == "M Fellaji; F Pennerath"
    )


def test_parse_authors_single():
    assert parse_authors("Doe, John") == "John Doe"


def test_parse_authors_no_comma():
    assert parse_authors("John Doe") == "John Doe"


def test_parse_authors_empty():
    assert parse_authors("") == ""
