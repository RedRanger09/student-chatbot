"""
Query normalization for intent routing and retrieval.

Expands campus abbreviations, cleans punctuation/spacing, and
produces a stable string for keyword / fuzzy scoring.
"""

from __future__ import annotations

import re
import unicodedata

# Word-boundary abbreviation expansions (lowercase keys).
_ABBREVIATIONS: dict[str, str] = {
    "clg": "college",
    "uni": "university",
    "univ": "university",
    "dept": "department",
    "prof": "professor",
    "hod": "head of department",
    "sem": "semester",
    "cgpa": "gpa",
    "sgpa": "gpa",
    "wifi": "wi-fi",
    "wi fi": "wi-fi",
    "id card": "student id",
    "idcard": "student id",
    "marksheet": "transcript",
    "mark sheet": "transcript",
    "marks sheet": "transcript",
    "exam form": "examination registration",
    "backs": "backlogs",
    "arrear": "backlog",
    "arrears": "backlogs",
    "kt": "backlog",
    "kts": "backlogs",
    "lib": "library",
    "acad": "academic",
    "scholership": "scholarship",
    "attendence": "attendance",
    "libary": "library",
    "transript": "transcript",
    "acadmic": "academic",
    "calender": "calendar",
}

# Phrase replacements applied before token-level expansion (longest first).
# Use word-boundary regex so "hostel fees" is not turned into "hostel feess".
_PHRASE_REPLACEMENTS: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (
            (r"\bmark sheets?\b", "transcript"),
            (r"\bmarks sheets?\b", "transcript"),
            (r"\bexam forms?\b", "examination registration"),
            (r"\bid cards?\b", "student id"),
            (r"\bwi[\s-]?fi\b", "wi-fi"),
            (r"\bhead of dept\b", "head of department"),
            (r"\bfailed subjects?\b", "backlogs"),
            (r"\bhostel fee\b", "hostel fees"),
            (r"\btution\b", "tuition"),
            (r"\baccomodation\b", "accommodation"),
        ),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)

_MULTI_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s\-./+%]+", re.UNICODE)


def normalize_query(text: str) -> str:
    """
    Normalize a user message for routing / retrieval helpers.

    Steps: unicode fold → lowercase → phrase expand → abbreviate →
    light punctuation cleanup → collapse whitespace.
    """
    raw = (text or "").strip()
    if not raw:
        return ""

    cleaned = unicodedata.normalize("NFKC", raw).lower()
    cleaned = cleaned.replace("’", "'").replace("“", '"').replace("”", '"')

    for src, dst in _PHRASE_REPLACEMENTS:
        cleaned = re.sub(src, dst, cleaned)

    # Expand known abbreviations as whole tokens / short phrases.
    for src, dst in sorted(_ABBREVIATIONS.items(), key=lambda kv: len(kv[0]), reverse=True):
        cleaned = re.sub(rf"\b{re.escape(src)}\b", dst, cleaned)

    cleaned = _PUNCT.sub(" ", cleaned)
    cleaned = _MULTI_SPACE.sub(" ", cleaned).strip()
    return cleaned


def normalization_trace(original: str) -> dict[str, str]:
    """Small debug payload for routing logs."""
    return {
        "original": (original or "")[:240],
        "normalized": normalize_query(original)[:240],
    }
