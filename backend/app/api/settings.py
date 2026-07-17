"""AI / LLM settings endpoints for the Settings UI."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, SecretStr

from backend.app.services.llm.gemini_provider import GeminiProvider
from backend.app.services.llm.provider_factory import get_provider_factory
from backend.app.services.runtime_config import get_runtime_config_store
from config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


class LLMSettingsModel(BaseModel):
    provider: Literal["auto", "gemini", "lmstudio"] = "auto"
    gemini_model: str = "gemini-2.5-flash"
    # Empty until env / Settings configures a LAN, tunnel, or public HTTPS URL.
    lmstudio_base_url: str = ""
    lmstudio_model: str = "auto"
    temperature: float = Field(0.2, ge=0.0, le=1.5)
    max_tokens: int = Field(1024, ge=64, le=8192)
    max_context_chunks: int = Field(5, ge=1, le=20)
    max_context_characters: int = Field(6000, ge=500, le=50000)
    # True when an optional server-side Gemini fallback key exists.
    # Never returns the key itself.
    has_google_api_key: bool = False
    gemini_server_fallback_enabled: bool = False
    has_lmstudio_auth: bool = False


class LLMSettingsUpdate(BaseModel):
    provider: Literal["auto", "gemini", "lmstudio"] | None = None
    gemini_model: str | None = None
    lmstudio_base_url: str | None = None
    lmstudio_model: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=1.5)
    max_tokens: int | None = Field(None, ge=64, le=8192)
    max_context_chunks: int | None = Field(None, ge=1, le=20)
    max_context_characters: int | None = Field(None, ge=500, le=50000)


class ProviderTestRequest(BaseModel):
    provider: Literal["gemini", "lmstudio"]
    # Optional user Gemini key for testing (never stored).
    api_key: SecretStr | None = None


class ProviderTestResponse(BaseModel):
    provider: str
    status: str
    detail: str
    model: str | None = None
    available_models: list[str] = Field(default_factory=list)


class GeminiValidateRequest(BaseModel):
    api_key: SecretStr


class GeminiValidateResponse(BaseModel):
    valid: bool
    status: str
    detail: str
    model: str | None = None


class ProviderHealthResponse(BaseModel):
    provider_mode: str
    lmstudio: dict[str, Any]
    gemini_server_fallback: bool


def _settings_model_from_cfg() -> LLMSettingsModel:
    cfg = get_runtime_config_store().get()
    settings = get_settings()
    fallback_enabled = bool(
        getattr(settings, "gemini_allow_server_fallback", True)
        and settings.google_api_key
    )
    return LLMSettingsModel(
        provider=cfg.provider,  # type: ignore[arg-type]
        gemini_model=cfg.gemini_model,
        lmstudio_base_url=cfg.lmstudio_base_url,
        lmstudio_model=cfg.lmstudio_model,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        max_context_chunks=cfg.max_context_chunks,
        max_context_characters=cfg.max_context_characters,
        has_google_api_key=bool(settings.google_api_key),
        gemini_server_fallback_enabled=fallback_enabled,
        has_lmstudio_auth=bool(getattr(settings, "lmstudio_api_key", None)),
    )


def _secret_value(value: SecretStr | None) -> str | None:
    if value is None:
        return None
    cleaned = (value.get_secret_value() or "").strip()
    return cleaned or None


@router.get("/llm", response_model=LLMSettingsModel)
def get_llm_settings() -> LLMSettingsModel:
    return _settings_model_from_cfg()


@router.put("/llm", response_model=LLMSettingsModel)
def update_llm_settings(body: LLMSettingsUpdate) -> LLMSettingsModel:
    from backend.app.services.llm.lmstudio_health import get_lmstudio_health_monitor

    payload = body.model_dump(exclude_unset=True)
    updated = get_runtime_config_store().update(**payload)
    # Endpoint / model changes should invalidate the cached health probe.
    monitor = get_lmstudio_health_monitor()
    monitor.invalidate()
    if "lmstudio_base_url" in payload:
        monitor.refresh(force=True)
    logger.info("LLM settings saved via API | provider=%s", updated.provider)
    return _settings_model_from_cfg()


@router.get("/llm/health", response_model=ProviderHealthResponse)
def llm_provider_health() -> ProviderHealthResponse:
    """
    Lightweight provider health for the Settings UI.

    Uses the cached remote LM Studio health monitor (same data as
    ``GET /api/providers/status``). Never returns API keys.
    """
    from backend.app.services.llm.lmstudio_health import get_lmstudio_health_monitor

    cfg = get_runtime_config_store().get()
    settings = get_settings()
    snapshot = get_lmstudio_health_monitor().get_snapshot()
    if not snapshot.checked_at:
        snapshot = get_lmstudio_health_monitor().refresh(force=True)
    public = snapshot.to_public_dict()
    status = public.get("status") or "offline"
    if status == "unconfigured":
        status = "offline"
    return ProviderHealthResponse(
        provider_mode=cfg.provider,
        lmstudio={
            "status": status if status in {"online", "offline"} else "offline",
            "detail": public.get("detail"),
            "model": public.get("model"),
            "endpoint": public.get("endpoint") or cfg.lmstudio_base_url,
            "available_models": list(public.get("available_models") or [])[:20],
            "latency_ms": public.get("latency_ms"),
            "checked_at": public.get("checked_at"),
        },
        gemini_server_fallback=bool(
            getattr(settings, "gemini_allow_server_fallback", True)
            and settings.google_api_key
        ),
    )


@router.post("/llm/validate-gemini", response_model=GeminiValidateResponse)
def validate_gemini_api_key(body: GeminiValidateRequest) -> GeminiValidateResponse:
    """
    Validate a user-supplied Gemini API key without storing it.

    The key is used only for this request and is never logged.
    """
    api_key = _secret_value(body.api_key)
    if not api_key:
        return GeminiValidateResponse(
            valid=False,
            status="missing_api_key",
            detail="Invalid API key",
            model=None,
        )
    provider = GeminiProvider(api_key=api_key, key_source="user")
    result = provider.validate_api_key()
    logger.info(
        "Gemini key validation | valid=%s | status=%s",
        result.get("valid"),
        result.get("status"),
    )
    return GeminiValidateResponse(
        valid=bool(result.get("valid")),
        status=str(result.get("status", "error")),
        detail=str(result.get("detail", "Invalid API key")),
        model=result.get("model"),
    )


@router.post("/llm/test", response_model=ProviderTestResponse)
def test_llm_provider(body: ProviderTestRequest) -> ProviderTestResponse:
    factory = get_provider_factory()
    user_key = _secret_value(body.api_key)
    try:
        provider = factory.get_named(body.provider, gemini_api_key=user_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result: dict[str, Any] = provider.healthcheck()
    return ProviderTestResponse(
        provider=str(result.get("provider", body.provider)),
        status=str(result.get("status", "error")),
        detail=str(result.get("detail", "")),
        model=result.get("model"),
        available_models=list(result.get("available_models") or []),
    )
