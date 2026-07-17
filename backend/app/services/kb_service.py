"""
Thin service wrappers over existing src/ business modules.

No retrieval / chunking / embedding logic lives here — only orchestration
for the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.settings import Settings, get_settings
from src.embeddings import EmbeddingService
from src.kb.institutional import InstitutionalKnowledgeBase
from src.retrieval_types import SearchResponse
from src.session.manager import SessionManager, get_session_manager
from src.utils.logger import get_logger

logger = get_logger(__name__)

APP_VERSION = "0.9.0"


@dataclass
class BytesUpload:
    """
    Framework-agnostic upload adapter for ``SessionKnowledgeBase.build``.

    Satisfies ``UploadedFileLike`` without depending on FastAPI or Streamlit.
    """

    name: str
    data: bytes

    def getbuffer(self) -> bytes:
        return self.data

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            return self.data
        return self.data[:size]


class KnowledgeBaseService:
    """Holds the shared Institutional KB and delegates to SessionManager."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.session_manager: SessionManager = get_session_manager()
        self.institutional_kb = InstitutionalKnowledgeBase(
            docs_path=self.settings.institutional_docs_path,
            index_path=self.settings.faiss_index_path,
            embedding_model=self.settings.embedding_model,
            top_k=self.settings.top_k,
            similarity_threshold=self.settings.similarity_threshold,
        )
        self._institutional_ready = False

    def bootstrap_institutional(self) -> None:
        """Load existing institutional index, or build if missing/corrupt."""
        if self.institutional_kb.index_exists():
            loaded = self.institutional_kb.load()
            if loaded:
                self._institutional_ready = True
                logger.info("Institutional KB loaded for API")
                return
            logger.warning("Institutional index corrupt/missing — rebuilding")
        else:
            logger.info("No institutional index — building")
        self.institutional_kb.build()
        self._institutional_ready = self.institutional_kb.vector_store.is_ready

    def health(self) -> dict[str, Any]:
        """Assemble health payload for GET /health."""
        stats = self.institutional_kb.stats()
        embedder = EmbeddingService.get_instance(self.settings.embedding_model)
        return {
            "status": "ok",
            "version": APP_VERSION,
            "embedding_model": embedder.model_name,
            "institutional_index_status": stats.index_status
            if self._institutional_ready or stats.index_status != "uninitialized"
            else ("ready" if self.institutional_kb.vector_store.is_ready else "unavailable"),
            "institutional_document_count": stats.document_count,
            "institutional_chunk_count": stats.chunk_count
            if stats.chunk_count
            else self.institutional_kb.vector_store.size,
            "active_sessions": self.session_manager.active_count(),
        }

    def search_institutional(self, query: str) -> SearchResponse:
        """Delegate to existing Institutional KB search."""
        return self.institutional_kb.search(query, top_k=self.settings.top_k)

    def search_session(self, session_id: str, query: str) -> SearchResponse:
        """
        Delegate to the session's Session KB.

        Raises:
            KeyError: Unknown / expired session.
            RuntimeError: Session has no uploaded document index.
        """
        kb = self.session_manager.get_knowledge_base(session_id)
        if kb is None:
            raise KeyError(f"Unknown or expired session_id: {session_id}")
        if not kb.has_index():
            raise RuntimeError(
                "No uploaded document for this session. Upload a file first."
            )
        return kb.search(query, top_k=self.settings.top_k)

    def upload_to_session(
        self,
        session_id: str,
        filename: str,
        data: bytes,
    ) -> dict[str, Any]:
        """
        Replace the session document with a new upload.

        Uses existing ``SessionKnowledgeBase.build`` — no duplicated pipeline.
        """
        kb = self.session_manager.get_knowledge_base(session_id)
        if kb is None:
            raise KeyError(f"Unknown or expired session_id: {session_id}")

        upload = BytesUpload(name=filename, data=data)
        result = kb.build(upload)
        return {
            "success": result.success,
            "session_id": session_id,
            "document_name": result.document_name,
            "chunk_count": result.chunk_count,
            "message": result.message,
        }


_kb_service: KnowledgeBaseService | None = None


def get_kb_service() -> KnowledgeBaseService:
    """Return the process-wide knowledge-base service."""
    global _kb_service
    if _kb_service is None:
        _kb_service = KnowledgeBaseService()
    return _kb_service
