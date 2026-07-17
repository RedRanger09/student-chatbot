"""
In-memory session store for SessionKnowledgeBase instances.

Framework-independent: no FastAPI / Streamlit imports.
Each client session owns one temporary Session KB that is never persisted.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from config.settings import Settings, get_settings
from src.kb.session import SessionKnowledgeBase
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_SESSION_TTL_SECONDS = 60 * 60  # 1 hour of inactivity


@dataclass
class SessionRecord:
    """One client session and its in-memory Session KB."""

    session_id: str
    knowledge_base: SessionKnowledgeBase
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        """Update last-accessed timestamp."""
        self.last_accessed_at = time.time()


class SessionManager:
    """
    Lightweight in-memory session manager.

    Responsibilities:
        - create session
        - retrieve session
        - clear session KB
        - expire inactive sessions

    Session KBs remain in memory only and disappear when cleared or expired.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    ) -> None:
        self._settings = settings or get_settings()
        self._ttl_seconds = ttl_seconds
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = threading.RLock()

    def create_session(self) -> str:
        """Create a new session with an empty SessionKnowledgeBase."""
        self.expire_inactive()
        session_id = str(uuid.uuid4())
        kb = SessionKnowledgeBase(
            embedding_model=self._settings.embedding_model,
            top_k=self._settings.top_k,
            similarity_threshold=self._settings.similarity_threshold,
            upload_folder=self._settings.upload_folder,
        )
        record = SessionRecord(session_id=session_id, knowledge_base=kb)
        with self._lock:
            self._sessions[session_id] = record
        logger.info("Session created: %s", session_id)
        return session_id

    def get_session(self, session_id: str) -> SessionRecord | None:
        """Return a session record, or None if missing / expired."""
        self.expire_inactive()
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            record.touch()
            return record

    def get_knowledge_base(self, session_id: str) -> SessionKnowledgeBase | None:
        """Return the Session KB for ``session_id``, if present."""
        record = self.get_session(session_id)
        return record.knowledge_base if record else None

    def clear_session(self, session_id: str) -> bool:
        """
        Clear the Session KB for ``session_id`` but keep the session alive.

        Returns:
            True if the session existed.
        """
        record = self.get_session(session_id)
        if record is None:
            return False
        record.knowledge_base.clear()
        logger.info("Session KB cleared: %s", session_id)
        return True

    def delete_session(self, session_id: str) -> bool:
        """Remove a session entirely (destroys its in-memory KB)."""
        with self._lock:
            record = self._sessions.pop(session_id, None)
        if record is None:
            return False
        record.knowledge_base.clear()
        logger.info("Session deleted: %s", session_id)
        return True

    def expire_inactive(self) -> int:
        """
        Drop sessions idle longer than ``ttl_seconds``.

        Returns:
            Number of expired sessions removed.
        """
        now = time.time()
        expired: list[str] = []
        with self._lock:
            for sid, record in self._sessions.items():
                if now - record.last_accessed_at > self._ttl_seconds:
                    expired.append(sid)
            for sid in expired:
                record = self._sessions.pop(sid)
                record.knowledge_base.clear()
        if expired:
            logger.info("Expired %s inactive session(s)", len(expired))
        return len(expired)

    def active_count(self) -> int:
        """Number of sessions currently held in memory."""
        with self._lock:
            return len(self._sessions)


# Process-wide singleton used by the API layer.
_session_manager: SessionManager | None = None
_manager_lock = threading.Lock()


def get_session_manager() -> SessionManager:
    """Return the shared ``SessionManager`` instance."""
    global _session_manager
    if _session_manager is None:
        with _manager_lock:
            if _session_manager is None:
                _session_manager = SessionManager()
    return _session_manager
