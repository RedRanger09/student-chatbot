"""
Chat HTTP endpoint — thin adapter over ChatService.

No orchestration / formatting / routing logic lives here.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.models.chat_models import ChatTurnRequest
from backend.app.models.schemas import ChatMessageModel, ChatRequest, ChatResponse
from backend.app.services.chat_service import ChatServiceError, get_chat_service
from backend.app.services.llm.provider_context import bind_gemini_api_key
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["chat"])


def _extract_api_key(value: object) -> str | None:
    if value is None:
        return None
    get_secret = getattr(value, "get_secret_value", None)
    raw = get_secret() if callable(get_secret) else str(value)
    cleaned = (raw or "").strip()
    return cleaned or None


def _to_turn_request(body: ChatRequest) -> ChatTurnRequest:
    return ChatTurnRequest(
        message=body.message,
        conversation_id=body.conversation_id,
        session_id=body.session_id,
        api_key=_extract_api_key(body.api_key),
    )


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    """
    Accept a user message and return an assistant reply.

    Optional ``api_key`` is a client-supplied Gemini key for this request only.
    It is never logged or persisted.
    """
    from backend.app.services.llm.provider_context import get_request_gemini_api_key

    service = get_chat_service()
    turn = _to_turn_request(body)
    previous = get_request_gemini_api_key()
    try:
        bind_gemini_api_key(turn.api_key)
        result = service.process_message(turn)
    except ChatServiceError as exc:
        logger.warning("ChatService error: %s", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    finally:
        bind_gemini_api_key(previous)

    return ChatResponse(
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        role=result.role,
        content=result.content,
        status=result.status,
        mode=result.mode,
        source=result.source,
        streaming_supported=result.streaming_supported,
        timestamp=result.timestamp,
        metadata=result.metadata,
        user_message=ChatMessageModel(**result.user_message),
        assistant_message=ChatMessageModel(**result.assistant_message),
    )


@router.post("/chat/stream")
def chat_stream(body: ChatRequest) -> StreamingResponse:
    """
    Server-Sent Events stream for progressive assistant replies.

    Event payload shapes (JSON after ``data: ``):
      {"event":"start", ...}
      {"event":"token","delta":"..."}
      {"event":"done", ...full ChatResponse fields...}
      {"event":"error","detail":"...","status_code":400}
    """
    service = get_chat_service()
    turn = _to_turn_request(body)

    def event_generator() -> Iterator[str]:
        # Bind per-iteration (StreamingResponse may hop contexts between yields).
        # Do not use Token.reset — that caused post-success "Unexpected streaming failure".
        bind_gemini_api_key(turn.api_key)
        try:
            for payload in service.process_message_stream(turn):
                # Re-bind before each yield resume so provider selection mid-stream
                # still sees the user key if the Context was replaced.
                bind_gemini_api_key(turn.api_key)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except ChatServiceError as exc:
            err = {
                "event": "error",
                "detail": exc.message,
                "status_code": exc.status_code,
            }
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat_stream failure: %s", exc)
            err = {
                "event": "error",
                "detail": "Unexpected streaming failure",
                "status_code": 500,
            }
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        finally:
            bind_gemini_api_key(None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
