"""
Institutional Knowledge Base — persistent FAISS-backed store.

Pipeline: load documents → chunk → embed → FAISS → disk persistence.
If an index already exists on disk, it is loaded instead of rebuilt.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.chunking import Chunker, TextChunk
from src.embeddings import EmbeddingService
from src.retrieval_types import (
    NO_RELEVANT_INSTITUTIONAL_MESSAGE,
    SearchResponse,
    filter_by_similarity,
    hits_from_search_hits,
)
from src.utils.document_loader import load_documents_from_directory
from src.utils.helpers import ensure_dir
from src.utils.logger import get_logger
from src.vector_store import (
    DEFAULT_MANIFEST_FILENAME,
    ChunkMetadata,
    VectorStore,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class InstitutionalKBStats:
    """Summary statistics for logging and CLI display."""

    document_count: int
    chunk_count: int
    embedding_model: str
    index_status: str
    index_path: str


class InstitutionalKnowledgeBase:
    """
    Manages the persistent institutional document index.

    Public API:
        build()  — ingest docs, chunk, embed, save FAISS
        load()   — load existing FAISS + metadata from disk
        search() — embed query and return top-k hits
    """

    def __init__(
        self,
        docs_path: Path,
        index_path: Path,
        embedding_model: str = "all-MiniLM-L6-v2",
        chunk_size: int = 500,
        chunk_overlap: int = 75,
        top_k: int = 5,
        similarity_threshold: float = 0.35,
    ) -> None:
        """
        Args:
            docs_path: Directory containing institutional source documents.
            index_path: Directory for the persistent FAISS index.
            embedding_model: Sentence Transformers model name.
            chunk_size: Target words per chunk.
            chunk_overlap: Overlap words between chunks.
            top_k: Default retrieval depth before threshold filtering.
            similarity_threshold: Minimum similarity to keep a hit.
        """
        self.docs_path = Path(docs_path)
        self.index_path = Path(index_path)
        self.embedding_model_name = embedding_model
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.chunker = Chunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.embedder = EmbeddingService.get_instance(model_name=embedding_model)
        self.vector_store = VectorStore(index_dir=self.index_path)
        self._document_count = 0
        self._chunk_count = 0
        self._status = "uninitialized"

        logger.debug(
            "InstitutionalKnowledgeBase initialized (docs=%s, index=%s)",
            self.docs_path,
            self.index_path,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> InstitutionalKBStats:
        """
        Load every supported document, chunk, embed, build FAISS, and persist.

        Returns:
            Stats describing the built index.
        """
        ensure_dir(self.index_path)
        ensure_dir(self.docs_path)

        documents = load_documents_from_directory(self.docs_path)
        if not documents:
            logger.warning(
                "No institutional documents found in %s — index not built",
                self.docs_path,
            )
            self._document_count = 0
            self._chunk_count = 0
            self._status = "empty"
            return self.stats()

        all_chunks: list[TextChunk] = []
        for doc in documents:
            chunks = self.chunker.chunk_document(
                text=doc.text,
                document_name=doc.document_name,
                source_path=doc.source_path,
            )
            all_chunks.extend(chunks)

        logger.info(
            "Chunk count: %s (from %s documents)",
            len(all_chunks),
            len(documents),
        )

        if not all_chunks:
            logger.warning("Documents produced zero chunks — index not built")
            self._document_count = len(documents)
            self._chunk_count = 0
            self._status = "empty"
            return self.stats()

        texts = [c.text for c in all_chunks]
        logger.info("Embedding progress: starting encode of %s chunks", len(texts))
        vectors = self.embedder.embed_documents(texts)

        metadatas = [
            ChunkMetadata(
                text=c.text,
                document_name=c.document_name,
                chunk_id=c.chunk_id,
                source_path=c.source_path,
            )
            for c in all_chunks
        ]

        self.vector_store.clear()
        self.vector_store.create(dimension=int(vectors.shape[1]))
        self.vector_store.add(vectors, metadatas)
        self.vector_store.save(self.index_path)

        self._document_count = len(documents)
        self._chunk_count = len(all_chunks)
        self._status = "built"
        self._write_manifest()

        logger.info(
            "Institutional KB build complete | docs=%s | chunks=%s | model=%s",
            self._document_count,
            self._chunk_count,
            self.embedding_model_name,
        )
        return self.stats()

    def load(self) -> bool:
        """
        Load an existing FAISS index from disk.

        Returns:
            True if the index loaded successfully.
        """
        ok = self.vector_store.load(self.index_path)
        if not ok:
            self._status = "missing_or_corrupt"
            return False

        manifest = self._read_manifest()
        self._chunk_count = self.vector_store.size
        self._document_count = int(manifest.get("document_count", 0))
        if self._document_count == 0 and self._chunk_count > 0:
            # Derive unique document count from metadata if manifest is old/missing.
            self._document_count = len(self.vector_store.unique_document_names())

        self._status = "loaded"
        logger.info(
            "Institutional KB loaded | docs=%s | chunks=%s | model=%s",
            self._document_count,
            self._chunk_count,
            self.embedding_model_name,
        )
        return True

    def search(self, query: str, top_k: int | None = None) -> SearchResponse:
        """
        Embed ``query`` and return filtered top-k institutional chunks.

        Results below ``similarity_threshold`` are discarded. When none remain,
        ``message`` explains that no relevant content was found.
        """
        if not query or not query.strip():
            logger.warning("Empty search query ignored")
            return SearchResponse(results=[], message="Please enter a non-empty query.")

        if not self.vector_store.is_ready:
            logger.warning("Search skipped: institutional index is not ready")
            return SearchResponse(
                results=[],
                message="Institutional index is not ready.",
            )

        k = top_k if top_k is not None else self.top_k
        started = time.perf_counter()
        logger.info("Search request: %r (top_k=%s)", query[:120], k)

        query_vector = self.embedder.embed_query(query.strip())
        raw_hits = self.vector_store.search(query_vector, top_k=k)
        hits = hits_from_search_hits(raw_hits)
        response = filter_by_similarity(
            hits,
            self.similarity_threshold,
            empty_message=NO_RELEVANT_INSTITUTIONAL_MESSAGE,
        )

        latency_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "Search complete | kept=%s | latency_ms=%.2f | scores=%s",
            len(response.results),
            latency_ms,
            [round(h.similarity_score, 4) for h in response.results],
        )
        return response

    def index_exists(self) -> bool:
        """Return True if a persisted institutional index is present on disk."""
        return VectorStore.index_exists(self.index_path)

    def stats(self) -> InstitutionalKBStats:
        """Return current KB statistics for logging / CLI."""
        return InstitutionalKBStats(
            document_count=self._document_count,
            chunk_count=self._chunk_count if self._chunk_count else self.vector_store.size,
            embedding_model=self.embedding_model_name,
            index_status=self._status,
            index_path=str(self.index_path),
        )

    # ------------------------------------------------------------------
    # Backward-compatible aliases (Phase 1 placeholder names)
    # ------------------------------------------------------------------

    def build_index(self) -> InstitutionalKBStats:
        """Alias for ``build()``."""
        return self.build()

    def query(self, question: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Alias returning plain dicts for older callers."""
        response = self.search(question, top_k=top_k)
        return [hit.to_dict() for hit in response.results]

    # ------------------------------------------------------------------
    # Manifest helpers
    # ------------------------------------------------------------------

    def _manifest_path(self) -> Path:
        return self.index_path / DEFAULT_MANIFEST_FILENAME

    def _write_manifest(self) -> None:
        payload = {
            "document_count": self._document_count,
            "chunk_count": self._chunk_count,
            "embedding_model": self.embedding_model_name,
            "index_status": self._status,
        }
        ensure_dir(self.index_path)
        self._manifest_path().write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def _read_manifest(self) -> dict[str, Any]:
        path = self._manifest_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read manifest %s: %s", path, exc)
            return {}
