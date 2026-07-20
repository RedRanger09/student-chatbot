"""Client / device identity helpers (browser-scoped chat isolation)."""

from __future__ import annotations

from fastapi import Header, HTTPException


CLIENT_ID_HEADER = "X-Client-Id"
_MAX_CLIENT_ID_LEN = 128


def normalize_client_id(raw: str | None) -> str:
    """Sanitize a client id from header or request body."""
    cleaned = (raw or "").strip()
    if not cleaned:
        return ""
    # Reject control characters / absurd lengths.
    if any(ord(ch) < 32 for ch in cleaned):
        return ""
    return cleaned[:_MAX_CLIENT_ID_LEN]


def require_client_id(
    x_client_id: str | None = Header(default=None, alias=CLIENT_ID_HEADER),
) -> str:
    """
    FastAPI dependency: require ``X-Client-Id`` for conversation endpoints.

    Each browser generates a stable UUID in localStorage and sends it on
    every API call so chat history stays private to that device.
    """
    client_id = normalize_client_id(x_client_id)
    if not client_id:
        raise HTTPException(
            status_code=400,
            detail="Missing X-Client-Id header. Refresh the page and try again.",
        )
    return client_id


def optional_client_id(
    x_client_id: str | None = Header(default=None, alias=CLIENT_ID_HEADER),
) -> str:
    """FastAPI dependency: optional client id (chat can still create owned chats)."""
    return normalize_client_id(x_client_id)
