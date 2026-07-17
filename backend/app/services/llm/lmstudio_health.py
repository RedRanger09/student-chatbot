"""Cached LM Studio health monitoring for remote / tunnel endpoints."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ProviderHealthSnapshot:
    """Sanitized health snapshot (never includes API keys)."""

    online: bool = False
    status: str = "offline"  # online | offline | unconfigured | error
    detail: str = ""
    model: str | None = None
    endpoint: str = ""
    available_models: list[str] = field(default_factory=list)
    checked_at: float = 0.0
    latency_ms: float | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "status": "online" if self.online else (
                "unconfigured" if self.status == "unconfigured" else "offline"
            ),
            "detail": self.detail,
            "model": self.model,
            "endpoint": self.endpoint,
            "available_models": list(self.available_models)[:20],
            "checked_at": self.checked_at,
            "latency_ms": self.latency_ms,
        }


class LMStudioHealthMonitor:
    """
    Periodically probe ``GET {endpoint}/models`` and cache the result.

    Used by Auto provider selection and ``/api/providers/status`` so every
    chat turn does not open a fresh remote connection when unnecessary.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot = ProviderHealthSnapshot(
            status="unconfigured",
            detail="LM Studio endpoint is not configured.",
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._interval_s = 30.0

    def start(self, interval_seconds: float | None = None) -> None:
        from config.settings import get_settings

        settings = get_settings()
        self._interval_s = float(
            interval_seconds
            if interval_seconds is not None
            else settings.lmstudio_health_interval_seconds
        )
        self._interval_s = max(5.0, self._interval_s)
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name="lmstudio-health-monitor",
                daemon=True,
            )
            self._thread.start()
        # Immediate first probe so status is warm after boot.
        self.refresh(force=True)
        logger.info(
            "LMStudioHealthMonitor started | interval_s=%.1f",
            self._interval_s,
        )

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        logger.info("LMStudioHealthMonitor stopped")

    def get_snapshot(self) -> ProviderHealthSnapshot:
        with self._lock:
            return ProviderHealthSnapshot(
                online=self._snapshot.online,
                status=self._snapshot.status,
                detail=self._snapshot.detail,
                model=self._snapshot.model,
                endpoint=self._snapshot.endpoint,
                available_models=list(self._snapshot.available_models),
                checked_at=self._snapshot.checked_at,
                latency_ms=self._snapshot.latency_ms,
            )

    def is_online(self) -> bool:
        return self.get_snapshot().online

    def refresh(self, *, force: bool = False) -> ProviderHealthSnapshot:
        """Probe LM Studio now (or return cache when fresh and not forced)."""
        if not force:
            snap = self.get_snapshot()
            age = time.time() - snap.checked_at if snap.checked_at else 1e9
            if age < min(10.0, self._interval_s / 2):
                return snap

        started = time.perf_counter()
        from backend.app.services.llm.lmstudio_provider import LMStudioProvider
        from backend.app.services.runtime_config import get_runtime_llm_config

        cfg = get_runtime_llm_config()
        endpoint = (cfg.lmstudio_base_url or "").strip()
        if not endpoint:
            snapshot = ProviderHealthSnapshot(
                online=False,
                status="unconfigured",
                detail=(
                    "LM Studio endpoint is not configured. "
                    "Set LM_STUDIO_ENDPOINT or enter a URL in AI Settings."
                ),
                endpoint="",
                checked_at=time.time(),
            )
            self._store(snapshot)
            return snapshot

        provider = LMStudioProvider()
        try:
            result = provider.healthcheck()
            latency_ms = (time.perf_counter() - started) * 1000.0
            connected = result.get("status") == "connected"
            snapshot = ProviderHealthSnapshot(
                online=connected,
                status="online" if connected else (
                    "error" if result.get("status") == "error" else "offline"
                ),
                detail=str(result.get("detail") or ""),
                model=result.get("model"),
                endpoint=endpoint,
                available_models=list(result.get("available_models") or []),
                checked_at=time.time(),
                latency_ms=round(latency_ms, 2),
            )
            if connected:
                logger.info(
                    "LMStudioHealthMonitor online | endpoint=%s | model=%s | "
                    "latency_ms=%.1f",
                    endpoint,
                    snapshot.model,
                    latency_ms,
                )
            else:
                logger.warning(
                    "LMStudioHealthMonitor offline | endpoint=%s | status=%s | "
                    "latency_ms=%.1f",
                    endpoint,
                    snapshot.status,
                    latency_ms,
                )
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.perf_counter() - started) * 1000.0
            logger.warning(
                "LMStudioHealthMonitor probe failed | endpoint=%s | error=%s | "
                "latency_ms=%.1f",
                endpoint,
                type(exc).__name__,
                latency_ms,
            )
            snapshot = ProviderHealthSnapshot(
                online=False,
                status="offline",
                detail="Remote LM Studio endpoint is currently offline.",
                endpoint=endpoint,
                checked_at=time.time(),
                latency_ms=round(latency_ms, 2),
            )

        self._store(snapshot)
        return snapshot

    def invalidate(self) -> None:
        """Force the next status read to re-probe (e.g. after Settings save)."""
        with self._lock:
            self._snapshot.checked_at = 0.0

    def _store(self, snapshot: ProviderHealthSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot

    def _loop(self) -> None:
        while not self._stop.wait(self._interval_s):
            try:
                self.refresh(force=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("LMStudioHealthMonitor loop error: %s", exc)


_monitor: LMStudioHealthMonitor | None = None
_monitor_lock = threading.Lock()


def get_lmstudio_health_monitor() -> LMStudioHealthMonitor:
    global _monitor
    if _monitor is None:
        with _monitor_lock:
            if _monitor is None:
                _monitor = LMStudioHealthMonitor()
    return _monitor
