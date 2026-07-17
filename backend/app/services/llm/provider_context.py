"""Request-scoped provider credentials (never persisted)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

# Client-supplied Gemini key for this request only. Never log or persist.
_request_gemini_api_key: ContextVar[str | None] = ContextVar(
    "request_gemini_api_key",
    default=None,
)


def get_request_gemini_api_key() -> str | None:
    """Return the per-request Gemini API key, if any."""
    value = _request_gemini_api_key.get()
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def bind_gemini_api_key(api_key: str | None) -> None:
    """
    Bind (or clear) the request Gemini key.

    Uses ``ContextVar.set`` only — never ``reset`` — because FastAPI
    ``StreamingResponse`` can resume generators in a different Context than
    the one that originally entered a ``with`` block. Resetting across
    contexts raises ``ValueError`` and was surfacing as
    "Unexpected streaming failure" after successful replies.
    """
    _request_gemini_api_key.set((api_key or "").strip() or None)


@contextmanager
def use_gemini_api_key(api_key: str | None) -> Iterator[None]:
    """
    Bind a client Gemini API key for the current request/task.

    The key must never be written to logs, disk, cookies, or analytics.
    """
    previous = _request_gemini_api_key.get()
    bind_gemini_api_key(api_key)
    try:
        yield
    finally:
        # Prefer set(previous) over Token.reset so streaming context switches
        # cannot raise ValueError after a successful response.
        try:
            _request_gemini_api_key.set(previous)
        except Exception:  # noqa: BLE001
            bind_gemini_api_key(None)
