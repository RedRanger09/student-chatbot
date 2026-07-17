"""
In-memory conversation store with a SQLite-ready shape.

Framework-independent. Persistence can later replace this implementation
without changing API response contracts.
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
    """Process-wide in-memory conversation repository."""

    def __init__(self) -> None:
        self._items: dict[str, Conversation] = {}
        self._lock = threading.RLock()

    def create(self, title: str = "New chat") -> Conversation:
        now = time.time()
        conversation = Conversation(
            id=str(uuid.uuid4()),
            title=title.strip() or "New chat",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._items[conversation.id] = conversation
        logger.info("Conversation created: %s", conversation.id)
        return conversation

    def list(self) -> list[Conversation]:
        with self._lock:
            items = list(self._items.values())
        items.sort(key=lambda c: c.updated_at, reverse=True)
        return items

    def get(self, conversation_id: str) -> Conversation | None:
        with self._lock:
            return self._items.get(conversation_id)

    def delete(self, conversation_id: str) -> bool:
        with self._lock:
            existed = self._items.pop(conversation_id, None) is not None
        if existed:
            logger.info("Conversation deleted: %s", conversation_id)
        return existed

    def clear_messages(self, conversation_id: str) -> Conversation | None:
        with self._lock:
            conversation = self._items.get(conversation_id)
            if conversation is None:
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


_store: ConversationStore | None = None
_store_lock = threading.Lock()


def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = ConversationStore()
    return _store
