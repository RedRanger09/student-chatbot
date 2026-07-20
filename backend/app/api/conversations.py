"""Conversation CRUD endpoints (in-memory; owner-scoped by X-Client-Id)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.models.schemas import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationSummary,
)
from backend.app.services.client_identity import require_client_id
from src.conversations.store import get_conversation_store

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
def list_conversations(
    client_id: str = Depends(require_client_id),
) -> list[ConversationSummary]:
    store = get_conversation_store()
    return [
        ConversationSummary(**c.to_summary())
        for c in store.list(owner_id=client_id)
    ]


@router.post("", response_model=ConversationDetail)
def create_conversation(
    body: ConversationCreateRequest | None = None,
    client_id: str = Depends(require_client_id),
) -> ConversationDetail:
    title = body.title if body else "New chat"
    conversation = get_conversation_store().create(title=title, owner_id=client_id)
    return ConversationDetail(**conversation.to_dict())


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    client_id: str = Depends(require_client_id),
) -> ConversationDetail:
    conversation = get_conversation_store().get_for_owner(conversation_id, client_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationDetail(**conversation.to_dict())


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    client_id: str = Depends(require_client_id),
) -> dict[str, bool | str]:
    ok = get_conversation_store().delete(conversation_id, owner_id=client_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "conversation_id": conversation_id}


@router.post("/{conversation_id}/clear", response_model=ConversationDetail)
def clear_conversation(
    conversation_id: str,
    client_id: str = Depends(require_client_id),
) -> ConversationDetail:
    conversation = get_conversation_store().clear_messages(
        conversation_id,
        owner_id=client_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationDetail(**conversation.to_dict())
