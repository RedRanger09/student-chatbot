"""
Session Knowledge Base — temporary in-memory FAISS store.

Holds a student-uploaded document for the current client session only.
Never persists the index or metadata to disk.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.chunking import Chunker
from src.embeddings import EmbeddingService
from src.retrieval_types import (
    NO_RELEVANT_SESSION_MESSAGE,
    SearchResponse,
    filter_by_similarity,
    hits_from_search_hits,
)
from src.utils.document_loader import SUPPORTED_EXTENSIONS, load_document
from src.utils.logger import get_logger
from src.utils.upload import UploadedFileLike, temporary_upload
from src.vector_store import ChunkMetadata, VectorStore

logger = get_logger(__name__)


@dataclass(frozen=True)
class SessionBuildResult:
    """Outcome of building a session index from an upload."""

    success: bool
    document_name: str
    chunk_count: int
    message: str
    embedding_ms: float = 0.0
    index_ms: float = 0.0


class SessionKnowledgeBase:
    """
    Per-session personal knowledge base over one uploaded document.

    Public API:
        build(uploaded_file) — load, chunk, embed, in-memory FAISS
        search(query, top_k=5) — filtered retrieval
        clear() — destroy in-memory index
        has_index() — whether a searchable index exists
    """

    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        chunk_size: int = 500,
        chunk_overlap: int = 75,
        top_k: int = 5,
        similarity_threshold: float = 0.35,
        upload_folder: Path | None = None,
    ) -> None:
        """
        Args:
            embedding_model: Shared Sentence Transformers model name.
            chunk_size: Target words per chunk (reuses ``Chunker``).
            chunk_overlap: Overlap words between chunks.
            top_k: Default retrieval depth before threshold filtering.
            similarity_threshold: Minimum similarity to keep a hit.
            upload_folder: Unused for persistence (kept for API compatibility).
                Temporary files are written via ``tempfile`` and deleted.
        """
        self.embedding_model_name = embedding_model
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.upload_folder = Path(upload_folder) if upload_folder else None

        self.chunker = Chunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        # Share the singleton embedding model with the Institutional KB.
        self.embedder = EmbeddingService.get_instance(model_name=embedding_model)
        # In-memory only: no index_dir → never save/load from disk.
        self.vector_store = VectorStore(index_dir=None)

        self._document_name: str | None = None
        self._chunk_count = 0
        self._status = "empty"

        logger.debug(
            "SessionKnowledgeBase initialized (model=%s, top_k=%s, threshold=%.3f)",
            embedding_model,
            top_k,
            similarity_threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, uploaded_file: UploadedFileLike | Path) -> SessionBuildResult:
        """
        Build an in-memory index from an uploaded document.

        Accepts an ``UploadedFileLike`` adapter (or path for non-UI tests).
        Replaces any previous session index. Never writes FAISS to disk.
        """
        # Replace previous session document entirely.
        self.clear()

        try:
            if isinstance(uploaded_file, Path):
                return self._build_from_path(uploaded_file)
            return self._build_from_upload(uploaded_file)
        except Exception as exc:  # noqa: BLE001 — never crash the UI
            logger.error("Session KB build failed: %s", exc)
            self.clear()
            return SessionBuildResult(
                success=False,
                document_name=getattr(uploaded_file, "name", str(uploaded_file)),
                chunk_count=0,
                message=f"Failed to process upload: {exc}",
            )

    def search(self, query: str, top_k: int | None = None) -> SearchResponse:
        """
        Embed ``query``, search the in-memory index, apply similarity filter.

        Returns structured hits sorted by similarity descending. If nothing
        passes the threshold, returns an empty result with a clear message.
        """
        if not self.has_index():
            logger.warning("Search skipped: session index is missing")
            return SearchResponse(
                results=[],
                message="No session index available. Please upload a document first.",
            )

        if not query or not query.strip():
            logger.warning("Empty session search query ignored")
            return SearchResponse(results=[], message="Please enter a non-empty query.")

        k = top_k if top_k is not None else self.top_k
        started = time.perf_counter()
        logger.info("Session search request: %r (top_k=%s)", query[:120], k)

        try:
            query_vector = self.embedder.embed_query(query.strip())
        except Exception as exc:  # noqa: BLE001
            logger.error("Session query embedding failed: %s", exc)
            return SearchResponse(
                results=[],
                message=f"Failed to embed query: {exc}",
            )

        raw_hits = self.vector_store.search(query_vector, top_k=k)
        hits = hits_from_search_hits(raw_hits)
        response = filter_by_similarity(
            hits,
            self.similarity_threshold,
            empty_message=NO_RELEVANT_SESSION_MESSAGE,
        )

        latency_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "Session search complete | kept=%s | latency_ms=%.2f | scores=%s",
            len(response.results),
            latency_ms,
            [round(h.similarity_score, 4) for h in response.results],
        )
        return response

    def clear(self) -> None:
        """Destroy the in-memory FAISS index and session metadata."""
        had_index = self.vector_store.is_ready
        self.vector_store.clear()
        self._document_name = None
        self._chunk_count = 0
        self._status = "empty"
        if had_index:
            logger.info("Session index cleared")
        else:
            logger.debug("Session clear() called with no active index")

    def has_index(self) -> bool:
        """Return True when an in-memory session index is ready for search."""
        return self.vector_store.is_ready

    @property
    def document_name(self) -> str | None:
        """Name of the currently indexed upload, if any."""
        return self._document_name

    @property
    def chunk_count(self) -> int:
        """Number of chunks in the current session index."""
        return self._chunk_count

    @property
    def status(self) -> str:
        """Human-readable index status: empty | ready | error."""
        return self._status

    # ------------------------------------------------------------------
    # Internal build helpers
    # ------------------------------------------------------------------

    def _build_from_upload(self, uploaded_file: UploadedFileLike) -> SessionBuildResult:
        name = getattr(uploaded_file, "name", "upload")
        suffix = Path(name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            msg = f"Unsupported file type '{suffix}'. Please upload PDF, DOCX, or TXT."
            logger.warning(msg)
            return SessionBuildResult(
                success=False,
                document_name=name,
                chunk_count=0,
                message=msg,
            )

        with temporary_upload(uploaded_file) as temp_path:
            # Preserve the original filename in metadata (temp path is opaque).
            return self._build_from_path(temp_path, display_name=Path(name).name)

    def _build_from_path(
        self,
        path: Path,
        display_name: str | None = None,
    ) -> SessionBuildResult:
        document_name = display_name or path.name
        suffix = Path(document_name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            msg = f"Unsupported file type '{suffix}'. Please upload PDF, DOCX, or TXT."
            logger.warning(msg)
            return SessionBuildResult(
                success=False,
                document_name=document_name,
                chunk_count=0,
                message=msg,
            )

        loaded = load_document(path)
        if loaded is None:
            msg = (
                f"Could not read '{document_name}'. "
                "The file may be empty, corrupt, or unsupported."
            )
            logger.warning(msg)
            return SessionBuildResult(
                success=False,
                document_name=document_name,
                chunk_count=0,
                message=msg,
            )

        # Prefer the original upload name over the temp filename.
        source_label = document_name
        chunks = self.chunker.chunk_document(
            text=loaded.text,
            document_name=source_label,
            source_path=f"session://{source_label}",
        )
        logger.info("Session chunk count: %s (document=%s)", len(chunks), source_label)

        if not chunks:
            msg = f"No text chunks produced from '{source_label}'."
            logger.warning(msg)
            return SessionBuildResult(
                success=False,
                document_name=source_label,
                chunk_count=0,
                message=msg,
            )

        texts = [c.text for c in chunks]
        embed_started = time.perf_counter()
        try:
            vectors = self.embedder.embed_documents(texts)
        except Exception as exc:  # noqa: BLE001
            logger.error("Session embedding failed: %s", exc)
            return SessionBuildResult(
                success=False,
                document_name=source_label,
                chunk_count=0,
                message=f"Embedding failed: {exc}",
            )
        embedding_ms = (time.perf_counter() - embed_started) * 1000.0
        logger.info("Session embedding time: %.2f ms", embedding_ms)

        metadatas = [
            ChunkMetadata(
                text=c.text,
                document_name=c.document_name,
                chunk_id=c.chunk_id,
                source_path=c.source_path,
            )
            for c in chunks
        ]

        index_started = time.perf_counter()
        self.vector_store.clear()
        self.vector_store.create(dimension=int(vectors.shape[1]))
        self.vector_store.add(vectors, metadatas)
        # Intentionally do NOT call vector_store.save() — in-memory only.
        index_ms = (time.perf_counter() - index_started) * 1000.0
        logger.info(
            "Session in-memory index created | vectors=%s | time_ms=%.2f",
            self.vector_store.size,
            index_ms,
        )

        self._document_name = source_label
        self._chunk_count = len(chunks)
        self._status = "ready"

        return SessionBuildResult(
            success=True,
            document_name=source_label,
            chunk_count=len(chunks),
            message=f"Indexed '{source_label}' ({len(chunks)} chunks) in memory.",
            embedding_ms=embedding_ms,
            index_ms=index_ms,
        )

    # ------------------------------------------------------------------
    # Backward-compatible aliases
    # ------------------------------------------------------------------

    def ingest(self, file_path: Path) -> SessionBuildResult:
        """Alias for building from a filesystem path."""
        return self.build(file_path)

    def query(self, question: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Alias returning plain dicts for older callers."""
        response = self.search(question, top_k=top_k)
        return [hit.to_dict() for hit in response.results]
