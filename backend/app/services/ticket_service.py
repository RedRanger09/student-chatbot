"""
Ticket Service — SQLite logging for escalation tickets.

Future analytics can reuse the ``escalation_tickets`` table.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from config.settings import get_settings
from src.utils.helpers import ensure_dir
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class EscalationTicket:
    """Persisted escalation ticket row."""

    ticket_id: str
    timestamp: float
    conversation_id: str | None
    category: str
    severity: str
    message: str
    knowledge_mode: str | None
    provider: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TicketService:
    """Create and read escalation tickets from SQLite."""

    def __init__(self, db_path: Path | None = None) -> None:
        settings = get_settings()
        self._db_path = Path(db_path) if db_path else Path(settings.sqlite_db_path)
        self._lock = threading.RLock()
        ensure_dir(self._db_path.parent)
        self._init_db()

    def create_ticket(
        self,
        *,
        conversation_id: str | None,
        category: str,
        severity: str,
        message: str,
        knowledge_mode: str | None = None,
        provider: str | None = None,
    ) -> EscalationTicket:
        ticket = EscalationTicket(
            ticket_id=str(uuid.uuid4()),
            timestamp=time.time(),
            conversation_id=conversation_id,
            category=category,
            severity=severity,
            message=(message or "")[:4000],
            knowledge_mode=knowledge_mode,
            provider=provider,
        )
        try:
            with self._lock:
                with self._connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO escalation_tickets (
                            ticket_id, timestamp, conversation_id, category,
                            severity, message, knowledge_mode, provider
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ticket.ticket_id,
                            ticket.timestamp,
                            ticket.conversation_id,
                            ticket.category,
                            ticket.severity,
                            ticket.message,
                            ticket.knowledge_mode,
                            ticket.provider,
                        ),
                    )
                    conn.commit()
            logger.info(
                "TicketService created ticket | id=%s | category=%s | severity=%s | "
                "conversation_id=%s",
                ticket.ticket_id,
                ticket.category,
                ticket.severity,
                ticket.conversation_id,
            )
            return ticket
        except Exception as exc:  # noqa: BLE001
            logger.error("TicketService create failed: %s", exc)
            # Return an in-memory ticket so the user still gets a safe response.
            return EscalationTicket(
                ticket_id=f"local-{ticket.ticket_id[:8]}",
                timestamp=ticket.timestamp,
                conversation_id=conversation_id,
                category=category,
                severity=severity,
                message=ticket.message,
                knowledge_mode=knowledge_mode,
                provider=provider,
            )

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS escalation_tickets (
                        ticket_id TEXT PRIMARY KEY,
                        timestamp REAL NOT NULL,
                        conversation_id TEXT,
                        category TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        message TEXT NOT NULL,
                        knowledge_mode TEXT,
                        provider TEXT
                    )
                    """
                )
                conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn


_ticket_service: TicketService | None = None
_ticket_lock = threading.Lock()


def get_ticket_service() -> TicketService:
    global _ticket_service
    if _ticket_service is None:
        with _ticket_lock:
            if _ticket_service is None:
                _ticket_service = TicketService()
    return _ticket_service
