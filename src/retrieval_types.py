"""
Shared retrieval result types and similarity filtering.

Used by both Institutional KB and Session KB so threshold logic
is not duplicated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.utils.logger import get_logger
from src.vector_store import SearchHit

logger = get_logger(__name__)

NO_RELEVANT_SESSION_MESSAGE = "No relevant content found in your uploaded document."
NO_RELEVANT_INSTITUTIONAL_MESSAGE = "No relevant content found in the institutional knowledge base."


@dataclass(frozen=True)
class RetrievalHit:
    """A single filtered retrieval result, sorted by similarity descending."""

    text: str
    document_name: str
    chunk_id: str
    similarity_score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for UI / logging."""
        return asdict(self)


@dataclass(frozen=True)
class SearchResponse:
    """
    Structured search response.

    When filtering removes every candidate, ``results`` is empty and
    ``message`` explains that no relevant content was found.
    """

    results: list[RetrievalHit]
    message: str | None = None

    @property
    def has_results(self) -> bool:
        return bool(self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "message": self.message,
            "has_results": self.has_results,
        }


def hits_from_search_hits(raw_hits: list[SearchHit]) -> list[RetrievalHit]:
    """Convert vector-store ``SearchHit`` rows into ``RetrievalHit`` objects."""
    converted: list[RetrievalHit] = []
    for hit in raw_hits:
        converted.append(
            RetrievalHit(
                text=hit.text,
                document_name=str(hit.metadata.get("document_name", "")),
                chunk_id=str(hit.metadata.get("chunk_id", "")),
                similarity_score=float(hit.score),
                metadata=dict(hit.metadata),
            )
        )
    return converted


def filter_by_similarity(
    hits: list[RetrievalHit],
    threshold: float,
    *,
    empty_message: str,
) -> SearchResponse:
    """
    Keep hits at or above ``threshold``, sorted by similarity descending.

    Args:
        hits: Candidate retrieval hits (already limited to top_k upstream).
        threshold: Minimum cosine / inner-product similarity.
        empty_message: Message used when nothing survives filtering.
    """
    kept = [h for h in hits if h.similarity_score >= threshold]
    kept.sort(key=lambda h: h.similarity_score, reverse=True)

    scores_log = ", ".join(f"{h.similarity_score:.4f}" for h in hits) or "none"
    logger.info(
        "Similarity filter | threshold=%.3f | candidates=%s | kept=%s | scores=[%s]",
        threshold,
        len(hits),
        len(kept),
        scores_log,
    )

    if not kept:
        return SearchResponse(results=[], message=empty_message)
    return SearchResponse(results=kept, message=None)
