"""
Runtime LLM / generation configuration.

Env-backed defaults come from ``config.settings``. The Settings UI can update
this in-memory overlay without restarting the process. Values are also
persisted to ``analytics/llm_runtime.json`` so they survive restarts.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Literal

from config.settings import PROJECT_ROOT, get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

ProviderMode = Literal["auto", "gemini", "lmstudio"]

_RUNTIME_PATH = PROJECT_ROOT / "analytics" / "llm_runtime.json"


@dataclass
class RuntimeLLMConfig:
    """Mutable generation settings used by the LLM layer."""

    provider: ProviderMode = "auto"
    gemini_model: str = "gemini-2.5-flash"
    # Empty until env / Settings UI configures a remote or LAN endpoint.
    lmstudio_base_url: str = ""
    lmstudio_model: str = "auto"
    temperature: float = 0.2
    max_tokens: int = 1024
    max_context_chunks: int = 5
    max_context_characters: int = 6000

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RuntimeConfigStore:
    """Thread-safe store for runtime LLM configuration."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._config = self._load_initial()

    def get(self) -> RuntimeLLMConfig:
        with self._lock:
            return RuntimeLLMConfig(**self._config.to_dict())

    def update(self, **kwargs: Any) -> RuntimeLLMConfig:
        with self._lock:
            data = self._config.to_dict()
            for key, value in kwargs.items():
                if key in data and value is not None:
                    data[key] = value
            # Normalize / clamp
            provider = str(data["provider"]).lower()
            if provider not in {"auto", "gemini", "lmstudio"}:
                provider = "auto"
            data["provider"] = provider
            data["temperature"] = float(max(0.0, min(1.5, float(data["temperature"]))))
            data["max_tokens"] = int(max(64, min(8192, int(data["max_tokens"]))))
            data["max_context_chunks"] = int(max(1, min(20, int(data["max_context_chunks"]))))
            data["max_context_characters"] = int(
                max(500, min(50000, int(data["max_context_characters"])))
            )
            data["gemini_model"] = str(data["gemini_model"]).strip() or "gemini-2.5-flash"
            data["lmstudio_model"] = str(data["lmstudio_model"]).strip() or "auto"
            base = str(data["lmstudio_base_url"]).strip().rstrip("/")
            data["lmstudio_base_url"] = base
            self._config = RuntimeLLMConfig(**data)
            self._persist()
            logger.info("Runtime LLM config updated | provider=%s", self._config.provider)
            return self.get()

    def _load_initial(self) -> RuntimeLLMConfig:
        settings = get_settings()
        config = RuntimeLLMConfig(
            provider=settings.llm_provider,  # type: ignore[arg-type]
            gemini_model=settings.gemini_model,
            lmstudio_base_url=settings.lmstudio_base_url,
            lmstudio_model=settings.lmstudio_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_context_chunks=settings.max_context_chunks,
            max_context_characters=settings.max_context_characters,
        )
        if _RUNTIME_PATH.exists():
            try:
                raw = json.loads(_RUNTIME_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    allowed = {f.name for f in fields(RuntimeLLMConfig)}
                    overlay = {k: v for k, v in raw.items() if k in allowed}
                    merged = {**config.to_dict(), **overlay}
                    config = RuntimeLLMConfig(**merged)
                    logger.info("Loaded runtime LLM config from %s", _RUNTIME_PATH)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not load runtime LLM config: %s", exc)
        return config

    def _persist(self) -> None:
        try:
            _RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
            _RUNTIME_PATH.write_text(
                json.dumps(self._config.to_dict(), indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not persist runtime LLM config: %s", exc)


_store: RuntimeConfigStore | None = None
_store_lock = threading.Lock()


def get_runtime_config_store() -> RuntimeConfigStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = RuntimeConfigStore()
    return _store


def get_runtime_llm_config() -> RuntimeLLMConfig:
    return get_runtime_config_store().get()
