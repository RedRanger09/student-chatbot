"""Institutional and session search endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.models.schemas import (
    SearchRequest,
    SearchResponseModel,
    SessionSearchRequest,
)
from backend.app.services.kb_service import get_kb_service
from src.retrieval_types import SearchResponse

router = APIRouter(prefix="/search", tags=["search"])


def _to_model(response: SearchResponse) -> SearchResponseModel:
    return SearchResponseModel(**response.to_dict())


@router.post("/institutional", response_model=SearchResponseModel)
def search_institutional(body: SearchRequest) -> SearchResponseModel:
    """Retrieve top chunks from the persistent Institutional KB."""
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty")

    service = get_kb_service()
    if not service.institutional_kb.vector_store.is_ready:
        raise HTTPException(
            status_code=503,
            detail="Institutional index is not ready.",
        )

    response = service.search_institutional(query)
    return _to_model(response)


@router.post("/session", response_model=SearchResponseModel)
def search_session(body: SessionSearchRequest) -> SearchResponseModel:
    """Retrieve top chunks from the in-memory Session KB for a client."""
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty")

    service = get_kb_service()
    try:
        response = service.search_session(body.session_id, query)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_model(response)
