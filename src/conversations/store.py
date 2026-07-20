"""
In-memory conversation store with a SQLite-ready shape.

Framework-independent. Persistence can later replace this implementation
without changing API response contracts.

Conversations are scoped by ``owner_id`` (browser client id) so devices
do not see each other's chat history.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from src.utils.logger import get_logger

logger = get_logger(__name__)

Role = Literal["user", "assistant", "system"]


@dataclass
class Message:
    id: str
    role: Role
    content: str
    created_at: float
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
            "meta": self.meta,
        }


@dataclass
class Conversation:
    id: str
    title: str
    created_at: float
    updated_at: float
    messages: list[Message] = field(default_factory=list)
    # Browser / device id from ``X-Client-Id``. Empty = legacy / unscoped.
    owner_id: str = ""

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.messages),
            "preview": self._preview(),
        }

    def to_dict(self) -> dict:
        return {
            **self.to_summary(),
            "messages": [m.to_dict() for m in self.messages],
        }

    def _preview(self) -> str:
        for msg in self.messages:
            if msg.role == "user" and msg.content.strip():
                text = msg.content.strip()
                return text if len(text) <= 80 else text[:77] + "..."
        return "New conversation"


class ConversationStore:
    """Process-wide in-memory conversation repository (owner-scoped)."""

    def __init__(self) -> None:
        self._items: dict[str, Conversation] = {}
        self._lock = threading.RLock()

    def create(self, title: str = "New chat", *, owner_id: str = "") -> Conversation:
        now = time.time()
        conversation = Conversation(
            id=str(uuid.uuid4()),
            title=title.strip() or "New chat",
            created_at=now,
            updated_at=now,
            owner_id=(owner_id or "").strip(),
        )
        with self._lock:
            self._items[conversation.id] = conversation
        logger.info(
            "Conversation created: %s | owner=%s",
            conversation.id,
            _owner_log(conversation.owner_id),
        )
        return conversation

    def list(self, *, owner_id: str | None = None) -> list[Conversation]:
        """
        List conversations.

        When ``owner_id`` is provided, only that owner's chats are returned.
        When omitted / empty, returns an empty list (never the global dump).
        """
        owner = (owner_id or "").strip()
        with self._lock:
            if not owner:
                items = []
            else:
                items = [c for c in self._items.values() if c.owner_id == owner]
        items.sort(key=lambda c: c.updated_at, reverse=True)
        return items

    def get(self, conversation_id: str) -> Conversation | None:
        with self._lock:
            return self._items.get(conversation_id)

    def get_for_owner(self, conversation_id: str, owner_id: str) -> Conversation | None:
        """Return conversation only if it belongs to ``owner_id``."""
        conversation = self.get(conversation_id)
        if conversation is None:
            return None
        if not self.is_owner(conversation, owner_id):
            return None
        return conversation

    @staticmethod
    def is_owner(conversation: Conversation, owner_id: str) -> bool:
        owner = (owner_id or "").strip()
        if not owner:
            return False
        return conversation.owner_id == owner

    def delete(self, conversation_id: str, *, owner_id: str = "") -> bool:
        with self._lock:
            conversation = self._items.get(conversation_id)
            if conversation is None:
                return False
            if owner_id and not self.is_owner(conversation, owner_id):
                return False
            del self._items[conversation_id]
        logger.info("Conversation deleted: %s", conversation_id)
        return True

    def clear_messages(
        self,
        conversation_id: str,
        *,
        owner_id: str = "",
    ) -> Conversation | None:
        with self._lock:
            conversation = self._items.get(conversation_id)
            if conversation is None:
                return None
            if owner_id and not self.is_owner(conversation, owner_id):
                return None
            conversation.messages.clear()
            conversation.title = "New chat"
            conversation.updated_at = time.time()
            return conversation

    def add_message(
        self,
        conversation_id: str,
        role: Role,
        content: str,
        meta: dict | None = None,
    ) -> Message | None:
        with self._lock:
            conversation = self._items.get(conversation_id)
            if conversation is None:
                return None
            message = Message(
                id=str(uuid.uuid4()),
                role=role,
                content=content,
                created_at=time.time(),
                meta=meta or {},
            )
            conversation.messages.append(message)
            conversation.updated_at = message.created_at
            if (
                role == "user"
                and conversation.title in {"New chat", "New conversation"}
                and content.strip()
            ):
                snippet = content.strip()
                conversation.title = snippet if len(snippet) <= 48 else snippet[:45] + "..."
            return message


def _owner_log(owner_id: str) -> str:
    """Short non-reversible tag for logs (never log full client ids if long)."""
    text = (owner_id or "").strip()
    if not text:
        return "(none)"
    if len(text) <= 8:
        return text
    return f"{text[:4]}…{text[-4:]}"


_store: ConversationStore | None = None
_store_lock = threading.Lock()


def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = ConversationStore()
    return _store
