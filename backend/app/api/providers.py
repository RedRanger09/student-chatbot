"""Provider status endpoints (cached health for remote LM Studio)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.services.llm.lmstudio_health import get_lmstudio_health_monitor
from backend.app.services.runtime_config import get_runtime_llm_config
from config.settings import get_settings

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProvidersStatusResponse(BaseModel):
    """Sanitized multi-provider status (never includes API keys)."""

    provider_mode: str
    lmstudio: dict[str, Any]
    gemini_server_fallback: bool
    auto_priority: list[str] = Field(
        default_factory=lambda: [
            "remote_lm_studio",
            "user_gemini_key",
            "optional_server_gemini",
        ]
    )


@router.get("/status", response_model=ProvidersStatusResponse)
def providers_status(refresh: bool = False) -> ProvidersStatusResponse:
    """
    Cached LM Studio health for Settings Online/Offline badges.

    Uses the background health monitor. Pass ``?refresh=true`` to force a probe.
    Never returns API keys or prompt content.
    """
    cfg = get_runtime_llm_config()
    settings = get_settings()
    monitor = get_lmstudio_health_monitor()
    snapshot = monitor.refresh(force=refresh) if refresh else monitor.get_snapshot()
    # Warm cache on first hit after boot if monitor has not probed yet.
    if not snapshot.checked_at:
        snapshot = monitor.refresh(force=True)

    public = snapshot.to_public_dict()
    # Map unconfigured → offline for the existing UI badge.
    if public.get("status") == "unconfigured":
        public["status"] = "offline"

    return ProvidersStatusResponse(
        provider_mode=cfg.provider,
        lmstudio=public,
        gemini_server_fallback=bool(
            getattr(settings, "gemini_allow_server_fallback", True)
            and settings.google_api_key
        ),
    )
