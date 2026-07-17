"""Session lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.models.schemas import ClearSessionResponse, SessionCreateResponse
from backend.app.services.kb_service import get_kb_service

router = APIRouter(tags=["session"])


@router.post("/session", response_model=SessionCreateResponse)
def create_session() -> SessionCreateResponse:
    """Create a new client session with an empty Session KB."""
    session_id = get_kb_service().session_manager.create_session()
    return SessionCreateResponse(session_id=session_id)


@router.delete("/session/{session_id}", response_model=ClearSessionResponse)
def clear_session(session_id: str) -> ClearSessionResponse:
    """Clear the in-memory Session KB for ``session_id``."""
    ok = get_kb_service().session_manager.clear_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown or expired session_id")
    return ClearSessionResponse(
        success=True,
        session_id=session_id,
        message="Session knowledge base cleared.",
    )
