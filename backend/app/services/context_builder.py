"""
Context Builder — turns retrieved chunks into grounded prompt context.

Does not call any LLM. Only cleans, deduplicates, and truncates chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.app.services.runtime_config import get_runtime_llm_config
from src.retrieval_types import RetrievalHit
from src.utils.logger import get_logger

logger = get_logger(__name__)

_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class ContextSource:
    """One source passage included in the built context."""

    document_name: str
    chunk_id: str
    similarity_score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_name": self.document_name,
            "chunk_id": self.chunk_id,
            "similarity_score": self.similarity_score,
            "text": self.text,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BuiltContext:
    """Output of the Context Builder."""

    formatted_context: str
    sources: list[ContextSource]
    statistics: dict[str, Any]

    @property
    def is_empty(self) -> bool:
        return not self.sources or not self.formatted_context.strip()


class ContextBuilder:
    """
    Build a compact, de-duplicated context string from retrieval hits.

    Limits come from runtime config (MAX_CONTEXT_CHUNKS / MAX_CONTEXT_CHARACTERS).
    """

    def build(
        self,
        hits: list[RetrievalHit],
        *,
        max_chunks: int | None = None,
        max_characters: int | None = None,
    ) -> BuiltContext:
        cfg = get_runtime_llm_config()
        chunk_limit = max_chunks if max_chunks is not None else cfg.max_context_chunks
        char_limit = (
            max_characters if max_characters is not None else cfg.max_context_characters
        )

        # Sort by similarity descending
        ordered = sorted(hits, key=lambda h: h.similarity_score, reverse=True)

        selected: list[ContextSource] = []
        seen_text: set[str] = set()
        total_chars = 0

        for hit in ordered:
            if len(selected) >= chunk_limit:
                break
            text = _normalize_text(hit.text)
            if not text:
                continue
            # Prefer substantive body text when mixed with TOC/metadata crumbs.
            if _looks_like_metadata_only(text) and any(
                not _looks_like_metadata_only(_normalize_text(h.text)) for h in ordered
            ):
                continue
            dedupe_key = re.sub(r"\s+", " ", text.lower())
            if dedupe_key in seen_text:
                continue

            # Respect character budget (keep at least one chunk if possible).
            projected = total_chars + len(text) + 80  # overhead for labels
            if selected and projected > char_limit:
                break

            if not selected and len(text) > char_limit:
                text = text[: char_limit - 3].rstrip() + "..."

            seen_text.add(dedupe_key)
            selected.append(
                ContextSource(
                    document_name=hit.document_name or "Unknown document",
                    chunk_id=hit.chunk_id or "",
                    similarity_score=float(hit.similarity_score),
                    text=text,
                    metadata=dict(hit.metadata),
                )
            )
            total_chars += len(text)

        formatted = _format_context_block(selected)
        stats = {
            "input_hits": len(hits),
            "selected_chunks": len(selected),
            "context_characters": len(formatted),
            "max_context_chunks": chunk_limit,
            "max_context_characters": char_limit,
            "top_similarity": selected[0].similarity_score if selected else None,
        }
        logger.info(
            "ContextBuilder | input=%s selected=%s chars=%s top=%.4f",
            stats["input_hits"],
            stats["selected_chunks"],
            stats["context_characters"],
            stats["top_similarity"] if stats["top_similarity"] is not None else -1.0,
        )
        return BuiltContext(
            formatted_context=formatted,
            sources=selected,
            statistics=stats,
        )


def _normalize_text(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return ""
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    cleaned = _BLANK_LINES_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def _looks_like_metadata_only(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return True
    if len(cleaned) < 40:
        return True
    lower = cleaned.lower()
    if any(
        marker in lower
        for marker in ("table of contents", "page no", "page number")
    ) and len(cleaned) < 180:
        return True
    alpha = sum(1 for c in cleaned if c.isalpha())
    return alpha < 20


def _format_context_block(sources: list[ContextSource]) -> str:
    if not sources:
        return ""
    parts: list[str] = []
    for index, src in enumerate(sources, start=1):
        parts.append(
            f"[Source {index}] Document: {src.document_name} | "
            f"Chunk: {src.chunk_id} | Similarity: {src.similarity_score:.4f}\n"
            f"{src.text}"
        )
    return "\n\n".join(parts)
