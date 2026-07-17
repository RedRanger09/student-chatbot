"""
Limited conversation memory for multi-turn LLM prompts.

Loads only the most recent user/assistant turns from the conversation
store. Never dumps the full thread into a single prompt blob.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from config.settings import get_settings
from src.conversations.store import ConversationStore
from src.utils.logger import get_logger

logger = get_logger(__name__)

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class HistoryTurn:
    """One prior turn eligible for the LLM context window."""

    role: Role
    content: str
    created_at: float = 0.0


def get_max_history_messages() -> int:
    """Configurable cap (default 8)."""
    try:
        return max(0, int(get_settings().max_history_messages))
    except Exception:  # noqa: BLE001
        return 8


def get_memory_idle_seconds() -> int:
    """Seconds of inactivity before conversational memory is cleared (0 = never)."""
    try:
        return max(0, int(get_settings().memory_idle_seconds))
    except Exception:  # noqa: BLE001
        return 7200


def load_recent_history(
    store: ConversationStore,
    conversation_id: str,
    *,
    max_messages: int | None = None,
    exclude_message_ids: set[str] | None = None,
) -> list[HistoryTurn]:
    """
    Return up to ``max_messages`` recent user/assistant turns.

    The current user turn (already persisted) should be excluded so it is
    not duplicated in the prompt. After prolonged inactivity, returns [].
    """
    limit = get_max_history_messages() if max_messages is None else max(0, int(max_messages))
    if limit <= 0:
        return []

    conversation = store.get(conversation_id)
    if conversation is None:
        return []

    exclude = exclude_message_ids or set()
    selected: list[HistoryTurn] = []
    for message in conversation.messages:
        if message.id in exclude:
            continue
        if message.role not in ("user", "assistant"):
            continue
        content = (message.content or "").strip()
        if not content:
            continue
        selected.append(
            HistoryTurn(
                role=message.role,  # type: ignore[arg-type]
                content=content,
                created_at=float(getattr(message, "created_at", 0.0) or 0.0),
            )
        )

    idle = get_memory_idle_seconds()
    if idle > 0 and selected:
        last_prior = selected[-1].created_at
        if last_prior > 0 and (time.time() - last_prior) > idle:
            logger.info(
                "ConversationMemory idle expiry | conversation_id=%s | "
                "idle_s=%.0f | threshold=%s | clearing memory",
                conversation_id,
                time.time() - last_prior,
                idle,
            )
            return []

    # Keep only the trailing window.
    window = selected[-limit:]
    logger.info(
        "ConversationMemory | conversation_id=%s | available=%s | used=%s | max=%s",
        conversation_id,
        len(selected),
        len(window),
        limit,
    )
    return window


def history_as_dicts(history: list[HistoryTurn]) -> list[dict[str, str]]:
    """Serialize history for provider / metadata payloads."""
    return [{"role": turn.role, "content": turn.content} for turn in history]


def truncate_for_prompt(text: str, limit: int = 1200) -> str:
    """Bound a single history turn so prompts stay bounded."""
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."
