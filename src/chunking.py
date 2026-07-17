"""
Document chunking utilities.

Splits document text with recursive character separators, targeting
approximately 500-word chunks with 75-word overlap.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Prefer larger semantic units first, then fall back to finer splits.
_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", " ", "")


@dataclass(frozen=True)
class TextChunk:
    """A single chunk ready for embedding and indexing."""

    text: str
    document_name: str
    chunk_id: str
    source_path: str


class Chunker:
    """
    Recursive character splitter measured in words.

    Splits by paragraph / line / sentence / word boundaries while keeping
    each chunk near ``chunk_size`` words with ``chunk_overlap`` overlap.
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 75) -> None:
        """
        Args:
            chunk_size: Target words per chunk (approximately).
            chunk_overlap: Overlap in words between consecutive chunks.
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        logger.debug(
            "Chunker initialized (size=%s words, overlap=%s words)",
            chunk_size,
            chunk_overlap,
        )

    def chunk_document(
        self,
        text: str,
        document_name: str,
        source_path: str,
    ) -> list[TextChunk]:
        """
        Split ``text`` into overlapping chunks with metadata.

        Empty chunks are discarded. ``chunk_id`` is ``{stem}_{index:04d}``.
        """
        raw_parts = self._split_text(text)
        nonempty = [part.strip() for part in raw_parts if part and part.strip()]

        stem = document_name.rsplit(".", 1)[0] if document_name else "doc"
        chunks: list[TextChunk] = []
        for index, part in enumerate(nonempty):
            chunks.append(
                TextChunk(
                    text=part,
                    document_name=document_name,
                    chunk_id=f"{stem}_{index:04d}",
                    source_path=source_path,
                )
            )

        logger.debug(
            "Chunked %s into %s chunks",
            document_name,
            len(chunks),
        )
        return chunks

    def chunk(self, text: str) -> list[str]:
        """
        Split text into chunk strings without metadata.

        Provided for simple callers; prefer ``chunk_document`` for indexing.
        """
        return self._split_text(text)

    def _split_text(self, text: str) -> list[str]:
        """Recursively split ``text`` into ~chunk_size-word pieces."""
        cleaned = (text or "").strip()
        if not cleaned:
            return []
        return self._recursive_split(cleaned, list(_SEPARATORS))

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """
        LangChain-style recursive split, sized by word count.

        If the text already fits, return it. Otherwise split on the first
        usable separator and merge pieces into overlapping windows.
        """
        if self._word_count(text) <= self.chunk_size:
            return [text] if text.strip() else []

        if not separators:
            # Last resort: hard-split by words.
            return self._window_by_words(text.split())

        separator = separators[0]
        remaining = separators[1:]

        if separator == "":
            # Character-level fallback when even spaces are insufficient.
            return self._window_by_chars(text)

        splits = text.split(separator) if separator else list(text)
        # Re-attach separator except for the empty-string case (handled above).
        pieces: list[str] = []
        for i, part in enumerate(splits):
            if not part:
                continue
            if i < len(splits) - 1 and separator:
                pieces.append(part + separator)
            else:
                pieces.append(part)

        return self._merge_pieces(pieces, remaining)

    def _merge_pieces(self, pieces: list[str], remaining_separators: list[str]) -> list[str]:
        """Merge split pieces into overlapping chunks near the target size."""
        chunks: list[str] = []
        current: list[str] = []
        current_words = 0

        for piece in pieces:
            piece_words = self._word_count(piece)

            # Oversized piece: recurse with finer separators.
            if piece_words > self.chunk_size:
                if current:
                    chunks.append(self._join(current).strip())
                    current = []
                    current_words = 0
                chunks.extend(self._recursive_split(piece.strip(), remaining_separators))
                continue

            if current_words + piece_words > self.chunk_size and current:
                chunks.append(self._join(current).strip())
                # Keep overlap from the end of the completed chunk.
                overlap_text = self._tail_words(self._join(current), self.chunk_overlap)
                current = [overlap_text] if overlap_text else []
                current_words = self._word_count(overlap_text) if overlap_text else 0

            current.append(piece)
            current_words += piece_words

        if current:
            joined = self._join(current).strip()
            if joined:
                chunks.append(joined)

        return [c for c in chunks if c.strip()]

    def _window_by_words(self, words: list[str]) -> list[str]:
        """Hard windowing when recursive separators cannot reduce size."""
        if not words:
            return []
        step = max(1, self.chunk_size - self.chunk_overlap)
        windows: list[str] = []
        for start in range(0, len(words), step):
            window = words[start : start + self.chunk_size]
            if window:
                windows.append(" ".join(window))
            if start + self.chunk_size >= len(words):
                break
        return windows

    def _window_by_chars(self, text: str) -> list[str]:
        """Character-level fallback for extremely dense text."""
        # Approximate: ~5 characters per word on average.
        size = self.chunk_size * 5
        overlap = self.chunk_overlap * 5
        step = max(1, size - overlap)
        windows: list[str] = []
        for start in range(0, len(text), step):
            window = text[start : start + size].strip()
            if window:
                windows.append(window)
            if start + size >= len(text):
                break
        return windows

    @staticmethod
    def _word_count(text: str) -> int:
        return len(text.split()) if text and text.strip() else 0

    @staticmethod
    def _join(parts: list[str]) -> str:
        return "".join(parts)

    @staticmethod
    def _tail_words(text: str, n: int) -> str:
        """Return the last ``n`` words of ``text``."""
        if n <= 0:
            return ""
        words = text.split()
        if not words:
            return ""
        return " ".join(words[-n:])
