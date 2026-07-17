"""
Citation Builder — structured source attribution for grounded answers.

Independent of generation: never edits the LLM answer, only builds
citation metadata from retrieved chunks for the Response Formatter / UI.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from src.retrieval_types import RetrievalHit
from src.utils.logger import get_logger

logger = get_logger(__name__)

SourceType = Literal["institutional", "uploaded_notes"]

_CATEGORY_LABELS: dict[str, str] = {
    "admissions": "Admissions",
    "scholarships": "Scholarships",
    "fees": "Fees",
    "academics": "Academics",
    "examinations": "Examinations",
    "academic_calendar": "Academic Calendar",
    "hostel": "Hostel",
    "library": "Library",
    "student_services": "Student Services",
    "erp": "ERP",
    "certificates": "Certificates",
    "policies": "Policies",
    "contacts": "Contacts",
    "campus_facilities": "Campus Facilities",
    "general_faq": "General FAQ",
}


@dataclass(frozen=True)
class CitationPassage:
    """One retrieved chunk preserved under a document-level citation."""

    chunk_id: str
    text: str
    similarity: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Citation:
    """Deduplicated document-level citation."""

    id: str
    document: str
    category: str
    chunk_ids: list[str]
    similarity: float
    source_type: SourceType
    retrieved_text: str
    passages: list[CitationPassage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "document": self.document,
            "category": self.category,
            "chunk_ids": list(self.chunk_ids),
            "similarity": self.similarity,
            "source_type": self.source_type,
            "retrieved_text": self.retrieved_text,
            "passages": [p.to_dict() for p in self.passages],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CitationBuildResult:
    """Output of the Citation Builder."""

    citations: list[Citation]
    statistics: dict[str, Any]

    def to_dicts(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self.citations]


class CitationBuilder:
    """
    Build structured citations from retrieval hits.

    Deduplicates by document: one citation per document with the highest
    similarity, all referenced chunk IDs, and every passage preserved.
    """

    def build(
        self,
        hits: list[RetrievalHit],
        *,
        source_type: SourceType = "institutional",
    ) -> CitationBuildResult:
        if not hits:
            logger.info("CitationBuilder | no hits — empty citations")
            return CitationBuildResult(
                citations=[],
                statistics={
                    "citation_count": 0,
                    "input_hits": 0,
                    "source_types": [],
                    "documents": [],
                },
            )

        grouped: dict[str, list[RetrievalHit]] = {}
        for hit in hits:
            key = _document_key(hit)
            grouped.setdefault(key, []).append(hit)

        citations: list[Citation] = []
        for key, group in grouped.items():
            group_sorted = sorted(
                group,
                key=lambda h: h.similarity_score,
                reverse=True,
            )
            best = group_sorted[0]
            document = _display_document_name(best.document_name or "Unknown document")
            category = _infer_category(
                best.document_name or "",
                source_type=source_type,
            )
            chunk_ids: list[str] = []
            seen_chunks: set[str] = set()
            passages: list[CitationPassage] = []

            for hit in group_sorted:
                chunk_id = (hit.chunk_id or "").strip() or "unknown"
                if chunk_id not in seen_chunks:
                    seen_chunks.add(chunk_id)
                    chunk_ids.append(chunk_id)
                text = (hit.text or "").strip()
                passages.append(
                    CitationPassage(
                        chunk_id=chunk_id,
                        text=text,
                        similarity=round(float(hit.similarity_score), 4),
                    )
                )

            meta = dict(best.metadata or {})
            meta.setdefault("source_path", meta.get("source_path"))
            meta["hit_count"] = len(group_sorted)
            meta["document_key"] = key

            citations.append(
                Citation(
                    id=str(uuid.uuid4()),
                    document=document,
                    category=category,
                    chunk_ids=chunk_ids,
                    similarity=round(float(best.similarity_score), 4),
                    source_type=source_type,
                    retrieved_text=(best.text or "").strip(),
                    passages=passages,
                    metadata=meta,
                )
            )

        # Highest similarity first for UI ordering
        citations.sort(key=lambda c: c.similarity, reverse=True)

        stats = {
            "citation_count": len(citations),
            "input_hits": len(hits),
            "source_types": sorted({c.source_type for c in citations}),
            "documents": [c.document for c in citations],
            "chunk_ids": [cid for c in citations for cid in c.chunk_ids],
            "similarity_scores": [c.similarity for c in citations],
        }
        logger.info(
            "CitationBuilder | citations=%s | hits=%s | source_types=%s | docs=%s | "
            "chunk_ids=%s | similarities=%s",
            stats["citation_count"],
            stats["input_hits"],
            stats["source_types"],
            stats["documents"],
            stats["chunk_ids"],
            stats["similarity_scores"],
        )
        return CitationBuildResult(citations=citations, statistics=stats)


def _document_key(hit: RetrievalHit) -> str:
    """Stable dedupe key for a document (prefer source_path, else name)."""
    path = ""
    if isinstance(hit.metadata, dict):
        path = str(hit.metadata.get("source_path") or "").strip()
    name = (hit.document_name or "").strip()
    if path:
        return path.lower()
    if name:
        return name.lower()
    return f"unknown::{(hit.chunk_id or '').strip().lower()}"


def _display_document_name(document_name: str) -> str:
    """
    Return a user-friendly document label.

    ``fees/fee_structure.md`` → ``fee_structure.md``
    ``Operating Systems Notes.pdf`` → unchanged
    """
    name = (document_name or "").strip() or "Unknown document"
    # Normalize path separators
    name = name.replace("\\", "/")
    if "/" in name:
        return name.rsplit("/", 1)[-1]
    return name


def _infer_category(document_name: str, *, source_type: SourceType) -> str:
    if source_type == "uploaded_notes":
        return "Uploaded Notes"

    name = (document_name or "").replace("\\", "/").strip()
    if "/" in name:
        folder = name.split("/", 1)[0].strip().lower()
        if folder in _CATEGORY_LABELS:
            return _CATEGORY_LABELS[folder]
        return _title_case_token(folder)

    # Flat filename fallback — try known category tokens in the name
    lower = name.lower()
    for key, label in _CATEGORY_LABELS.items():
        if key in lower or key.replace("_", " ") in lower:
            return label

    stem = re.sub(r"\.[^.]+$", "", name)
    if stem:
        return _title_case_token(stem.replace("_", " ").replace("-", " "))
    return "General"


def _title_case_token(value: str) -> str:
    cleaned = re.sub(r"[_\-]+", " ", (value or "").strip())
    if not cleaned:
        return "General"
    return " ".join(part.capitalize() for part in cleaned.split())
