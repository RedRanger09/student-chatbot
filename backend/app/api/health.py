"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.models.schemas import HealthResponse
from backend.app.services.kb_service import get_kb_service

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return API status, embedding model, and institutional index status."""
    payload = get_kb_service().health()
    return HealthResponse(**payload)
