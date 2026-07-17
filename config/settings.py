"""
Centralized application configuration.

Loads environment variables via python-dotenv and exposes a single
Settings dataclass used across the project. Paths are resolved relative
to the project root so nothing is hardcoded to a machine-specific location.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Project root: student-support-chatbot/
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# Load .env from the project root if present.
load_dotenv(PROJECT_ROOT / ".env")


def _env(key: str, default: str | None = None) -> str | None:
    """Read an environment variable, returning default when unset or empty."""
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_path(key: str, default: Path) -> Path:
    """
    Resolve a path from an environment variable.

    Relative paths are interpreted relative to PROJECT_ROOT.
    Absolute paths are used as-is.
    """
    raw = _env(key)
    if raw is None:
        return default
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _env_float(key: str, default: float) -> float:
    """Read a float environment variable with fallback."""
    raw = _env(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    """Read an int environment variable with fallback."""
    raw = _env(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_first(*keys: str, default: str | None = None) -> str | None:
    """Return the first non-empty env value among ``keys``."""
    for key in keys:
        value = _env(key)
        if value:
            return value
    return default


def _resolve_lm_studio_endpoint() -> str:
    """
    Remote / local OpenAI-compatible base URL (must include ``/v1``).

    Prefer ``LM_STUDIO_ENDPOINT``, then legacy ``LMSTUDIO_BASE_URL``.
    No localhost default — production must set a public tunnel or LAN URL.
    """
    raw = _env_first("LM_STUDIO_ENDPOINT", "LMSTUDIO_BASE_URL", default="") or ""
    return raw.strip().rstrip("/")


def _resolve_lm_studio_api_key() -> str | None:
    return _env_first("LM_STUDIO_API_KEY", "LMSTUDIO_API_KEY")


def _resolve_cors_origins() -> list[str]:
    """
    Comma-separated ``CORS_ORIGINS``.

    When unset, allow common local Next.js origins for development only.
    Deployments should set explicit Vercel / production origins.
    """
    raw = _env("CORS_ORIGINS")
    if raw:
        return [part.strip() for part in raw.split(",") if part.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


@dataclass(frozen=True)
class Settings:
    """
    Immutable application settings.

    API key has no default — it must be provided via environment.
    All other fields have sensible project-relative defaults.
    """

    google_api_key: str | None = field(default_factory=lambda: _env("GOOGLE_API_KEY"))
    embedding_model: str = field(
        default_factory=lambda: _env("EMBEDDING_MODEL", "all-MiniLM-L6-v2") or "all-MiniLM-L6-v2"
    )
    gemini_model: str = field(
        default_factory=lambda: _env("GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash"
    )
    faiss_index_path: Path = field(
        default_factory=lambda: _env_path("FAISS_INDEX_PATH", PROJECT_ROOT / "indexes")
    )
    log_level: str = field(
        default_factory=lambda: _env("LOG_LEVEL", "INFO") or "INFO"
    )
    upload_folder: Path = field(
        default_factory=lambda: _env_path("UPLOAD_FOLDER", PROJECT_ROOT / "uploads")
    )
    sqlite_db_path: Path = field(
        default_factory=lambda: _env_path(
            "SQLITE_DB_PATH", PROJECT_ROOT / "analytics" / "analytics.db"
        )
    )
    institutional_docs_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "knowledge_base"
    )
    logs_path: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")
    top_k: int = field(default_factory=lambda: _env_int("TOP_K", 5))
    similarity_threshold: float = field(
        default_factory=lambda: _env_float("SIMILARITY_THRESHOLD", 0.35)
    )
    # Context builder
    max_context_chunks: int = field(
        default_factory=lambda: _env_int("MAX_CONTEXT_CHUNKS", 5)
    )
    max_context_characters: int = field(
        default_factory=lambda: _env_int("MAX_CONTEXT_CHARACTERS", 6000)
    )
    # LLM generation
    llm_provider: str = field(
        default_factory=lambda: (_env("LLM_PROVIDER", "auto") or "auto").lower()
    )
    # OpenAI-compatible remote LM Studio / Ollama / vLLM base URL (…/v1).
    # Alias: LMSTUDIO_BASE_URL (legacy). No localhost hardcode.
    lmstudio_base_url: str = field(default_factory=_resolve_lm_studio_endpoint)
    lmstudio_model: str = field(
        default_factory=lambda: _env_first("LM_STUDIO_MODEL", "LMSTUDIO_MODEL", default="auto")
        or "auto"
    )
    # Optional bearer for authenticated tunnels / reverse proxies.
    # Alias: LMSTUDIO_API_KEY (legacy). Never expose to the frontend.
    lmstudio_api_key: str | None = field(default_factory=_resolve_lm_studio_api_key)
    lmstudio_timeout_seconds: float = field(
        default_factory=lambda: _env_float("LM_STUDIO_TIMEOUT_SECONDS", 120.0)
    )
    lmstudio_health_timeout_seconds: float = field(
        default_factory=lambda: _env_float("LM_STUDIO_HEALTH_TIMEOUT_SECONDS", 8.0)
    )
    lmstudio_max_retries: int = field(
        default_factory=lambda: _env_int("LM_STUDIO_MAX_RETRIES", 2)
    )
    lmstudio_health_interval_seconds: float = field(
        default_factory=lambda: _env_float("LM_STUDIO_HEALTH_INTERVAL_SECONDS", 30.0)
    )
    # When True and GOOGLE_API_KEY is set, Auto/Gemini may use the server key
    # only after the user's browser key is absent.
    gemini_allow_server_fallback: bool = field(
        default_factory=lambda: (_env("GEMINI_ALLOW_SERVER_FALLBACK", "true") or "true")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"}
    )
    cors_origins: list[str] = field(default_factory=_resolve_cors_origins)
    llm_temperature: float = field(
        default_factory=lambda: _env_float("LLM_TEMPERATURE", 0.2)
    )
    llm_max_tokens: int = field(default_factory=lambda: _env_int("LLM_MAX_TOKENS", 1024))
    # Multi-turn conversation memory (user+assistant turns fed to the LLM).
    max_history_messages: int = field(
        default_factory=lambda: _env_int("MAX_HISTORY_MESSAGES", 8)
    )
    # Drop conversational memory after this many seconds of inactivity (0 = never).
    memory_idle_seconds: int = field(
        default_factory=lambda: _env_int("MEMORY_IDLE_SECONDS", 7200)
    )

    def ensure_directories(self) -> None:
        """Create required runtime directories if they do not exist."""
        for path in (
            self.faiss_index_path,
            self.upload_folder,
            self.sqlite_db_path.parent,
            self.institutional_docs_path,
            self.logs_path,
        ):
            path.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """
    Return a Settings instance and ensure runtime directories exist.

    Call this from application entry points; do not mutate the returned object.
    """
    settings = Settings()
    settings.ensure_directories()
    return settings
