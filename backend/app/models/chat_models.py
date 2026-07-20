"""
Domain models for the chat orchestration layer.

These are framework-independent dataclasses used inside ChatService.
HTTP/Pydantic schemas live in ``backend.app.models.schemas``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ChatIntent = Literal[
    "institutional_faq",
    "personal_notes",
    "escalate",
    "out_of_scope",
]

VALID_INTENTS: frozenset[str] = frozenset(
    {
        "institutional_faq",
        "personal_notes",
        "escalate",
        "out_of_scope",
    }
)


@dataclass(frozen=True)
class ChatTurnRequest:
    """Normalized inbound chat request for ChatService."""

    message: str
    conversation_id: str | None = None
    session_id: str | None = None
    # Client-supplied Gemini key for this turn only. Never persisted.
    api_key: str | None = None
    # Browser device id from ``X-Client-Id`` — scopes conversation ownership.
    client_id: str | None = None


@dataclass
class SessionContext:
    """Lightweight session-notes context (no retrieval performed)."""

    has_notes: bool = False
    document_name: str | None = None


@dataclass(frozen=True)
class RouteDecision:
    """
    Structured routing decision from the Intent Router.

    Classification only — never contains an answer to the user question.
    """

    intent: ChatIntent
    confidence: float
    reason: str
    requires_upload: bool = False


@dataclass
class FormattedAssistantContent:
    """Markdown-ready assistant body produced by ResponseFormatter."""

    content: str
    mode: str = "placeholder"
    source: str | None = None
    status: str = "success"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatTurnResult:
    """
    Full orchestration result returned to the API layer.

    Contains both the expanded orchestration fields and the
    frontend-compatible message pair.
    """

    conversation_id: str
    message_id: str
    role: str
    content: str
    status: str
    mode: str
    source: str | None
    streaming_supported: bool
    timestamp: str
    metadata: dict[str, Any]
    user_message: dict[str, Any]
    assistant_message: dict[str, Any]
    latency_ms: float
