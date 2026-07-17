"""Conversation CRUD endpoints (in-memory; SQLite-ready contracts)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.models.schemas import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationSummary,
)
from src.conversations.store import get_conversation_store

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
def list_conversations() -> list[ConversationSummary]:
    store = get_conversation_store()
    return [ConversationSummary(**c.to_summary()) for c in store.list()]


@router.post("", response_model=ConversationDetail)
def create_conversation(body: ConversationCreateRequest | None = None) -> ConversationDetail:
    title = body.title if body else "New chat"
    conversation = get_conversation_store().create(title=title)
    return ConversationDetail(**conversation.to_dict())


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str) -> ConversationDetail:
    conversation = get_conversation_store().get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationDetail(**conversation.to_dict())


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, bool | str]:
    ok = get_conversation_store().delete(conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "conversation_id": conversation_id}


@router.post("/{conversation_id}/clear", response_model=ConversationDetail)
def clear_conversation(conversation_id: str) -> ConversationDetail:
    conversation = get_conversation_store().clear_messages(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationDetail(**conversation.to_dict())
