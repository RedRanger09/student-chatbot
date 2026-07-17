"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, SecretStr


class HealthResponse(BaseModel):
    status: str
    version: str
    embedding_model: str
    institutional_index_status: str
    institutional_document_count: int = 0
    institutional_chunk_count: int = 0
    active_sessions: int = 0


class SessionCreateResponse(BaseModel):
    session_id: str


class UploadResponse(BaseModel):
    success: bool
    session_id: str
    document_name: str
    chunk_count: int
    message: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)


class SessionSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)


class RetrievalHitModel(BaseModel):
    text: str
    document_name: str
    chunk_id: str
    similarity_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponseModel(BaseModel):
    results: list[RetrievalHitModel]
    message: str | None = None
    has_results: bool


class ErrorResponse(BaseModel):
    detail: str


class ClearSessionResponse(BaseModel):
    success: bool
    session_id: str
    message: str


# ---------------------------------------------------------------------------
# Conversations + chat (stable product contracts; generation is placeholder)
# ---------------------------------------------------------------------------


class ConversationCreateRequest(BaseModel):
    title: str = "New chat"


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: float
    updated_at: float
    message_count: int
    preview: str


class ChatMessageModel(BaseModel):
    id: str
    role: str
    content: str
    created_at: float
    meta: dict[str, Any] = Field(default_factory=dict)


class ConversationDetail(ConversationSummary):
    messages: list[ChatMessageModel] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None
    session_id: str | None = None
    # Optional per-request Gemini key from the browser. Never stored server-side.
    # SecretStr keeps the value out of logs / repr.
    api_key: SecretStr | None = None


class ChatResponse(BaseModel):
    """
    Stable chat response contract.

    Frontend-compatible fields (``user_message``, ``assistant_message``) are
    retained. Orchestration fields (``message_id``, ``content``, ``metadata``,
    etc.) are available for richer clients without breaking existing UI.
    """

    conversation_id: str
    message_id: str
    role: str = "assistant"
    content: str
    status: str = "success"
    mode: str = "placeholder"
    source: str | None = None
    streaming_supported: bool = True
    timestamp: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Retained for the current Next.js client — do not remove.
    user_message: ChatMessageModel
    assistant_message: ChatMessageModel
