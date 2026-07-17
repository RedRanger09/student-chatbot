"""
FAISS vector store with separate on-disk metadata persistence.

Vectors live in a FAISS index; chunk text and metadata live in a JSON
sidecar so metadata is never lost across save/load cycles.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from src.utils.helpers import ensure_dir
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_INDEX_FILENAME = "institutional.faiss"
DEFAULT_METADATA_FILENAME = "institutional_metadata.json"
DEFAULT_MANIFEST_FILENAME = "institutional_manifest.json"


@dataclass
class ChunkMetadata:
    """Metadata stored alongside each FAISS vector (same row order)."""

    text: str
    document_name: str
    chunk_id: str
    source_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChunkMetadata:
        return cls(
            text=str(data.get("text", "")),
            document_name=str(data.get("document_name", "")),
            chunk_id=str(data.get("chunk_id", "")),
            source_path=str(data.get("source_path", "")),
        )


@dataclass(frozen=True)
class SearchHit:
    """A single nearest-neighbor search result."""

    text: str
    metadata: dict[str, Any]
    score: float


class VectorStore:
    """
    FAISS IndexFlatIP store with JSON metadata sidecar.

    Embeddings are expected to be L2-normalized so inner product ≈ cosine.
    """

    def __init__(self, index_dir: Path | None = None) -> None:
        """
        Args:
            index_dir: Directory that will hold FAISS + metadata files.
        """
        self.index_dir = Path(index_dir) if index_dir is not None else None
        self._index: faiss.Index | None = None
        self._metadata: list[ChunkMetadata] = []
        self._dimension: int | None = None

    @property
    def size(self) -> int:
        """Number of vectors currently in the index."""
        if self._index is None:
            return 0
        return int(self._index.ntotal)

    @property
    def is_ready(self) -> bool:
        """True when an index with at least one vector is loaded."""
        return self._index is not None and self.size > 0

    @property
    def metadata(self) -> list[ChunkMetadata]:
        """Read-only view of metadata rows aligned with FAISS vector IDs."""
        return list(self._metadata)

    def unique_document_names(self) -> set[str]:
        """Return the set of distinct document names present in metadata."""
        return {m.document_name for m in self._metadata if m.document_name}

    def create(self, dimension: int) -> None:
        """Create an empty Inner-Product FAISS index of the given dimension."""
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self._index = faiss.IndexFlatIP(dimension)
        self._metadata = []
        self._dimension = dimension
        logger.info("Created empty FAISS IndexFlatIP (dim=%s)", dimension)

    def add(
        self,
        vectors: np.ndarray | list[list[float]],
        metadatas: list[dict[str, Any]] | list[ChunkMetadata] | None = None,
    ) -> None:
        """
        Add embeddings and aligned metadata rows.

        Args:
            vectors: Array of shape ``(n, dim)``.
            metadatas: Optional list of length ``n`` (dicts or ChunkMetadata).
        """
        array = np.asarray(vectors, dtype=np.float32)
        if array.ndim != 2:
            raise ValueError(f"Expected 2-D vectors, got shape {array.shape}")

        n, dim = array.shape
        if n == 0:
            logger.warning("add() called with zero vectors; nothing to do")
            return

        if self._index is None:
            self.create(dim)
        elif self._dimension != dim:
            raise ValueError(
                f"Vector dimension {dim} does not match index dimension {self._dimension}"
            )

        assert self._index is not None

        if metadatas is None:
            meta_rows = [
                ChunkMetadata(text="", document_name="", chunk_id="", source_path="")
                for _ in range(n)
            ]
        else:
            if len(metadatas) != n:
                raise ValueError(
                    f"metadata length {len(metadatas)} does not match vector count {n}"
                )
            meta_rows = [
                m if isinstance(m, ChunkMetadata) else ChunkMetadata.from_dict(m)
                for m in metadatas
            ]

        # FAISS requires contiguous float32.
        self._index.add(np.ascontiguousarray(array))
        self._metadata.extend(meta_rows)
        logger.info("Added %s vectors (total=%s)", n, self.size)

    def search(self, query_embedding: np.ndarray | list[float], top_k: int = 5) -> list[SearchHit]:
        """
        Search nearest neighbors for a query embedding.

        Returns:
            List of ``SearchHit`` with ``text``, ``metadata``, and ``score``.
        """
        if self._index is None or self.size == 0:
            logger.warning("Search requested but index is empty or missing")
            return []

        query = np.asarray(query_embedding, dtype=np.float32).reshape(1, -1)
        if query.shape[1] != self._dimension:
            raise ValueError(
                f"Query dim {query.shape[1]} does not match index dim {self._dimension}"
            )

        k = min(max(top_k, 1), self.size)
        scores, indices = self._index.search(np.ascontiguousarray(query), k)

        hits: list[SearchHit] = []
        for score, idx in zip(scores[0], indices[0], strict=True):
            if idx < 0 or idx >= len(self._metadata):
                continue
            meta = self._metadata[idx]
            hits.append(
                SearchHit(
                    text=meta.text,
                    metadata={
                        "document_name": meta.document_name,
                        "chunk_id": meta.chunk_id,
                        "source_path": meta.source_path,
                    },
                    score=float(score),
                )
            )
        return hits

    def save(self, index_dir: Path | None = None) -> None:
        """
        Persist FAISS index and metadata JSON to ``index_dir``.

        Files written:
            - institutional.faiss
            - institutional_metadata.json
        """
        target = Path(index_dir) if index_dir is not None else self.index_dir
        if target is None:
            raise ValueError("index_dir is required to save the vector store")
        if self._index is None:
            raise RuntimeError("Cannot save: no FAISS index in memory")

        ensure_dir(target)
        faiss_path = target / DEFAULT_INDEX_FILENAME
        meta_path = target / DEFAULT_METADATA_FILENAME

        faiss.write_index(self._index, str(faiss_path))
        payload = [m.to_dict() for m in self._metadata]
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        self.index_dir = target
        logger.info(
            "Index saved | path=%s | vectors=%s | metadata_rows=%s",
            faiss_path,
            self.size,
            len(self._metadata),
        )

    def load(self, index_dir: Path | None = None) -> bool:
        """
        Load FAISS index and metadata from disk.

        Returns:
            True on success, False if files are missing or corrupt
            (without raising, so callers can fall back to rebuild).
        """
        target = Path(index_dir) if index_dir is not None else self.index_dir
        if target is None:
            logger.warning("Cannot load index: no index_dir configured")
            return False

        faiss_path = target / DEFAULT_INDEX_FILENAME
        meta_path = target / DEFAULT_METADATA_FILENAME

        if not faiss_path.exists() or not meta_path.exists():
            logger.info("No existing institutional index found under %s", target)
            return False

        try:
            index = faiss.read_index(str(faiss_path))
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("metadata file must contain a JSON list")

            metadata = [ChunkMetadata.from_dict(item) for item in raw]
            if index.ntotal != len(metadata):
                raise ValueError(
                    f"FAISS ntotal ({index.ntotal}) != metadata rows ({len(metadata)})"
                )

            self._index = index
            self._metadata = metadata
            self._dimension = int(index.d)
            self.index_dir = target
            logger.info(
                "Index loaded | path=%s | vectors=%s | dim=%s",
                faiss_path,
                self.size,
                self._dimension,
            )
            return True
        except Exception as exc:  # noqa: BLE001 — corrupt index must not crash
            logger.error("Corrupt or unreadable index under %s: %s", target, exc)
            self._index = None
            self._metadata = []
            self._dimension = None
            return False

    def clear(self) -> None:
        """Drop the in-memory index and metadata."""
        self._index = None
        self._metadata = []
        self._dimension = None

    @staticmethod
    def index_exists(index_dir: Path) -> bool:
        """Return True if both FAISS and metadata files exist."""
        return (index_dir / DEFAULT_INDEX_FILENAME).exists() and (
            index_dir / DEFAULT_METADATA_FILENAME
        ).exists()
