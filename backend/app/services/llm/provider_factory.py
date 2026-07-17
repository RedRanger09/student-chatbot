"""Provider factory with Auto / Gemini / LM Studio selection."""

from __future__ import annotations

import threading
from typing import Any

from backend.app.services.llm.base import LLMProvider
from backend.app.services.llm.gemini_provider import GeminiProvider
from backend.app.services.llm.lmstudio_provider import LMStudioProvider
from backend.app.services.llm.provider_context import get_request_gemini_api_key
from backend.app.services.runtime_config import get_runtime_llm_config
from config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ProviderUnavailableError(RuntimeError):
    """Raised when no usable provider can be selected."""


class ProviderOfflineError(ProviderUnavailableError):
    """Raised when an explicitly selected provider is offline."""


class ProviderFactory:
    """
    Resolve the active LLM provider in one place.

    ChatService / LLMService should only talk to this factory — never to
    Gemini or LM Studio directly.
    """

    def select_provider(self) -> tuple[LLMProvider, dict[str, Any]]:
        """
        Return ``(provider, selection_info)``.

        Selection rules
        ---------------
        Auto:
          1. Configured LM Studio endpoint if online
          2. User-supplied Gemini API key (request-scoped)
          3. Optional server Gemini fallback key
          4. Else: no provider available

        Gemini (explicit):
          User key → server fallback → error (no silent LM Studio switch)

        LM Studio (explicit):
          Online → use it; Offline → error (no silent Gemini switch)
        """
        cfg = get_runtime_llm_config()
        mode = (cfg.provider or "auto").lower()
        info: dict[str, Any] = {"mode": mode, "fallbacks": []}

        if mode == "gemini":
            return self._select_gemini_explicit(info)

        if mode == "lmstudio":
            return self._select_lmstudio_explicit(info)

        return self._select_auto(info)

    def _select_auto(self, info: dict[str, Any]) -> tuple[LLMProvider, dict[str, Any]]:
        from backend.app.services.llm.lmstudio_health import get_lmstudio_health_monitor

        lmstudio = LMStudioProvider()
        # Prefer cached remote health so Auto does not probe on every chat turn.
        monitor = get_lmstudio_health_monitor()
        snap = monitor.get_snapshot()
        if not snap.checked_at:
            snap = monitor.refresh(force=True)
        if snap.online:
            info["selected"] = "lmstudio"
            info["reason"] = "auto_lmstudio_online"
            info["endpoint_online"] = True
            logger.info(
                "ProviderFactory AUTO → lmstudio (cached online | latency_ms=%s)",
                snap.latency_ms,
            )
            return lmstudio, info
        info["fallbacks"].append(
            {
                "provider": "lmstudio",
                "health": {
                    "status": snap.status,
                    "detail": snap.detail,
                    "model": snap.model,
                },
            }
        )
        logger.info(
            "ProviderFactory AUTO: LM Studio offline (%s) — trying Gemini",
            snap.status,
        )

        user_key = get_request_gemini_api_key()
        if user_key:
            gemini = GeminiProvider(api_key=user_key, key_source="user")
            info["selected"] = "gemini"
            info["reason"] = "auto_user_gemini_key"
            info["gemini_key_source"] = "user"
            logger.info("ProviderFactory AUTO → gemini (user key)")
            return gemini, info
        info["fallbacks"].append({"provider": "gemini", "health": {"status": "no_user_key"}})

        if _server_gemini_fallback_enabled():
            gemini = GeminiProvider(key_source="server")
            if gemini.has_api_key:
                health = gemini.healthcheck()
                if health.get("status") == "connected":
                    info["selected"] = "gemini"
                    info["reason"] = "auto_server_gemini_fallback"
                    info["gemini_key_source"] = "server"
                    logger.info("ProviderFactory AUTO → gemini (server fallback)")
                    return gemini, info
                info["fallbacks"].append(
                    {"provider": "gemini_server", "health": _safe_health(health)}
                )
            else:
                info["fallbacks"].append(
                    {"provider": "gemini_server", "health": {"status": "missing_api_key"}}
                )

        logger.error("ProviderFactory AUTO: no providers available")
        raise ProviderUnavailableError("No AI provider available.")

    def _select_gemini_explicit(
        self,
        info: dict[str, Any],
    ) -> tuple[LLMProvider, dict[str, Any]]:
        user_key = get_request_gemini_api_key()
        if user_key:
            provider = GeminiProvider(api_key=user_key, key_source="user")
            info["selected"] = "gemini"
            info["reason"] = "explicit_gemini_user_key"
            info["gemini_key_source"] = "user"
            logger.info("ProviderFactory selected gemini (user key)")
            return provider, info

        if _server_gemini_fallback_enabled():
            provider = GeminiProvider(key_source="server")
            if provider.has_api_key:
                info["selected"] = "gemini"
                info["reason"] = "explicit_gemini_server_fallback"
                info["gemini_key_source"] = "server"
                logger.info("ProviderFactory selected gemini (server fallback)")
                return provider, info

        info["selected"] = None
        info["reason"] = "gemini_no_api_key"
        raise ProviderUnavailableError("No Gemini API key configured.")

    def _select_lmstudio_explicit(
        self,
        info: dict[str, Any],
    ) -> tuple[LLMProvider, dict[str, Any]]:
        from backend.app.services.llm.lmstudio_health import get_lmstudio_health_monitor

        provider = LMStudioProvider()
        # Explicit mode: verify now (and refresh cache) — never silently fall back.
        monitor = get_lmstudio_health_monitor()
        snap = monitor.refresh(force=True)
        if snap.online:
            info["selected"] = "lmstudio"
            info["reason"] = "explicit_lmstudio"
            info["endpoint_online"] = True
            logger.info("ProviderFactory selected lmstudio (explicit)")
            return provider, info

        info["selected"] = "lmstudio"
        info["reason"] = "explicit_lmstudio_offline"
        info["endpoint_online"] = False
        info["fallbacks"].append(
            {
                "provider": "lmstudio",
                "health": {
                    "status": snap.status,
                    "detail": snap.detail,
                    "model": snap.model,
                },
            }
        )
        logger.warning("ProviderFactory LM Studio offline — no silent fallback")
        raise ProviderOfflineError("Local AI server is currently offline.")

    def get_named(
        self,
        name: str,
        *,
        gemini_api_key: str | None = None,
    ) -> LLMProvider:
        """Return a provider by explicit name (for Test / Validate buttons)."""
        key = (name or "").lower()
        if key == "gemini":
            if gemini_api_key:
                return GeminiProvider(api_key=gemini_api_key, key_source="user")
            user_key = get_request_gemini_api_key()
            if user_key:
                return GeminiProvider(api_key=user_key, key_source="user")
            return GeminiProvider(key_source="server")
        if key in {"lmstudio", "lm_studio", "local"}:
            return LMStudioProvider()
        raise ValueError(f"Unknown provider: {name}")


def _server_gemini_fallback_enabled() -> bool:
    """Optional server Gemini key may be used when no user key is present."""
    settings = get_settings()
    if not getattr(settings, "gemini_allow_server_fallback", True):
        return False
    return bool(settings.google_api_key)


def _safe_health(health: dict[str, Any]) -> dict[str, Any]:
    """Copy health dict without any credential-like fields."""
    return {
        "status": health.get("status"),
        "detail": health.get("detail"),
        "model": health.get("model"),
    }


_factory: ProviderFactory | None = None
_factory_lock = threading.Lock()


def get_provider_factory() -> ProviderFactory:
    global _factory
    if _factory is None:
        with _factory_lock:
            if _factory is None:
                _factory = ProviderFactory()
    return _factory
