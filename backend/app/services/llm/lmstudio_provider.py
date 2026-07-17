"""LM Studio provider via OpenAI-compatible HTTP / HTTPS API."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any, Sequence

from backend.app.services.llm.base import LLMProvider, LLMResponse
from backend.app.services.llm.output_guard import (
    ANTI_TOOL_CALL_INSTRUCTION,
    looks_like_tool_call,
    message_has_tool_calls,
)
from backend.app.services.llm.prompts import (
    GENERAL_KNOWLEDGE_SYSTEM_PROMPT,
    GROUNDING_SYSTEM_PROMPT,
    build_general_user_prompt,
    build_user_prompt,
    history_as_chat_messages,
)
from backend.app.services.runtime_config import get_runtime_llm_config
from config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Treat these configured values as "use whatever LM Studio has loaded".
_AUTO_MODEL_TOKENS = frozenset({"", "auto", "*", "any", "default", "local", "loaded"})

_OFFLINE_MSG = "Local AI server is currently offline."


class LMStudioProvider(LLMProvider):
    """OpenAI-compatible generator (LM Studio, Ollama, vLLM, LocalAI, tunnels)."""

    name = "lmstudio"

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
        api_key: str | None = None,
        max_retries: int | None = None,
    ) -> None:
        cfg = get_runtime_llm_config()
        settings = get_settings()
        self._base_url = (base_url if base_url is not None else cfg.lmstudio_base_url).rstrip(
            "/"
        )
        self._model_name = model_name if model_name is not None else cfg.lmstudio_model
        self._timeout = float(
            timeout_seconds
            if timeout_seconds is not None
            else settings.lmstudio_timeout_seconds
        )
        self._health_timeout = float(settings.lmstudio_health_timeout_seconds)
        self._max_retries = int(
            max_retries if max_retries is not None else settings.lmstudio_max_retries
        )
        self._max_retries = max(0, min(5, self._max_retries))
        # Optional bearer for authenticated tunnels / reverse proxies.
        env_key = getattr(settings, "lmstudio_api_key", None)
        self._api_key = (api_key if api_key is not None else env_key) or None
        if self._api_key:
            self._api_key = str(self._api_key).strip() or None
        self._resolved_model_cache: tuple[float, str] | None = None
        self._resolved_model_ttl_s = 15.0

    @property
    def model_name(self) -> str:
        cfg = get_runtime_llm_config()
        configured = self._model_name if self._model_name is not None else cfg.lmstudio_model
        return str(configured or "auto")

    @property
    def base_url(self) -> str:
        cfg = get_runtime_llm_config()
        return (self._base_url or cfg.lmstudio_base_url or "").rstrip("/")

    def generate(
        self,
        context: str,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> LLMResponse:
        return self._chat(
            system_prompt=GROUNDING_SYSTEM_PROMPT,
            user_prompt=build_user_prompt(context=context, question=question),
            history=history,
            log_label="generate",
            context_chars=len(context or ""),
            stream=False,
        )

    def generate_general(
        self,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> LLMResponse:
        return self._chat(
            system_prompt=GENERAL_KNOWLEDGE_SYSTEM_PROMPT,
            user_prompt=build_general_user_prompt(question=question, history=history),
            history=history,
            log_label="generate_general",
            context_chars=0,
            stream=False,
        )

    def generate_stream(
        self,
        context: str,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> Iterator[str]:
        yield from self._chat_stream(
            system_prompt=GROUNDING_SYSTEM_PROMPT,
            user_prompt=build_user_prompt(context=context, question=question),
            history=history,
            log_label="generate_stream",
            context_chars=len(context or ""),
        )

    def generate_general_stream(
        self,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> Iterator[str]:
        yield from self._chat_stream(
            system_prompt=GENERAL_KNOWLEDGE_SYSTEM_PROMPT,
            user_prompt=build_general_user_prompt(question=question, history=history),
            history=history,
            log_label="generate_general_stream",
            context_chars=0,
        )

    def _require_endpoint(self) -> str:
        base = self.base_url
        if not base:
            raise RuntimeError(
                "LM Studio endpoint is not configured. "
                "Set LM_STUDIO_ENDPOINT or enter a URL in AI Settings."
            )
        return base

    def _chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        history: Sequence[dict[str, str]] | None,
        log_label: str,
        context_chars: int,
        stream: bool,
    ) -> LLMResponse:
        started = time.perf_counter()
        cfg = get_runtime_llm_config()
        base = self._require_endpoint()
        model_name = self.resolve_model()
        messages = _build_messages(system_prompt, history, user_prompt)

        content, usage = self._complete_once(
            base=base,
            model_name=model_name,
            messages=messages,
            temperature=float(cfg.temperature),
            max_tokens=int(cfg.max_tokens),
            log_label=log_label,
            context_chars=context_chars,
        )

        if looks_like_tool_call(content):
            logger.warning(
                "LMStudioProvider tool-call shaped output — retrying once | mode=%s",
                log_label,
            )
            retry_messages = list(messages)
            retry_messages.append(
                {
                    "role": "user",
                    "content": (
                        f"{ANTI_TOOL_CALL_INSTRUCTION}\n\n"
                        "Your previous reply was invalid. "
                        "Answer the student question again in Markdown only."
                    ),
                }
            )
            content, usage = self._complete_once(
                base=base,
                model_name=model_name,
                messages=retry_messages,
                temperature=min(float(cfg.temperature), 0.3),
                max_tokens=int(cfg.max_tokens),
                log_label=f"{log_label}_retry",
                context_chars=context_chars,
            )
            if looks_like_tool_call(content):
                raise RuntimeError(
                    "The local model returned a tool-call instead of an answer. "
                    "Please try again, or switch models in AI Settings."
                )

        if not content.strip():
            raise RuntimeError("LM Studio returned an empty generation response")

        latency_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "LMStudioProvider complete | mode=%s | model=%s | latency_ms=%.2f | tokens=%s",
            log_label,
            model_name,
            latency_ms,
            usage.get("total_tokens") if isinstance(usage, dict) else None,
        )
        return LLMResponse(
            content=content.strip(),
            provider=self.name,
            model=model_name,
            latency_ms=latency_ms,
            prompt_tokens=_usage_int(usage, "prompt_tokens"),
            completion_tokens=_usage_int(usage, "completion_tokens"),
            total_tokens=_usage_int(usage, "total_tokens"),
            raw={"usage": usage or {}, "mode": log_label},
        )

    def _complete_once(
        self,
        *,
        base: str,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        log_label: str,
        context_chars: int,
    ) -> tuple[str, dict[str, Any] | None]:
        payload: dict[str, Any] = {
            "model": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": False,
        }
        logger.info(
            "LMStudioProvider %s | endpoint=%s | model=%s | context_chars=%s | history=%s",
            log_label,
            base,
            model_name,
            context_chars,
            max(0, len(messages) - 2),
        )
        data = self._post_json(f"{base}/chat/completions", payload)
        content = _extract_message_content(data)
        usage = data.get("usage") if isinstance(data, dict) else None
        return content, usage if isinstance(usage, dict) else None

    def _chat_stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        history: Sequence[dict[str, str]] | None,
        log_label: str,
        context_chars: int,
    ) -> Iterator[str]:
        """
        Stream deltas to the client.

        Buffers the full completion first so tool-call shaped junk can be
        retried before any tokens reach the UI.
        """
        cfg = get_runtime_llm_config()
        base = self._require_endpoint()
        model_name = self.resolve_model()
        messages = _build_messages(system_prompt, history, user_prompt)
        payload: dict[str, Any] = {
            "model": model_name,
            "temperature": float(cfg.temperature),
            "max_tokens": int(cfg.max_tokens),
            "messages": messages,
            "stream": True,
        }
        logger.info(
            "LMStudioProvider %s | endpoint=%s | model=%s | context_chars=%s | history=%s",
            log_label,
            base,
            model_name,
            context_chars,
            len(history or []),
        )
        parts: list[str] = []
        try:
            for delta in self._post_sse_deltas(f"{base}/chat/completions", payload):
                if delta:
                    parts.append(delta)
        except Exception:
            if not parts:
                raise

        content = "".join(parts).strip()
        if looks_like_tool_call(content) or not content:
            logger.warning(
                "LMStudioProvider stream produced tool-call/empty output — "
                "retrying non-stream | mode=%s",
                log_label,
            )
            response = self._chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                history=history,
                log_label=f"{log_label}_guarded",
                context_chars=context_chars,
                stream=False,
            )
            content = response.content

        chunk_size = 48
        for i in range(0, len(content), chunk_size):
            yield content[i : i + chunk_size]

    def resolve_model(self, *, force_refresh: bool = False) -> str:
        """
        Pick a model id that LM Studio will accept.

        Preference order:
          1. Exact configured id (when present in /models)
          2. Fuzzy match against loaded models
          3. First model currently loaded (auto)
          4. Configured string as a last resort
        """
        now = time.monotonic()
        if (
            not force_refresh
            and self._resolved_model_cache is not None
            and (now - self._resolved_model_cache[0]) < self._resolved_model_ttl_s
        ):
            return self._resolved_model_cache[1]

        configured = (self.model_name or "").strip()
        available = self._list_available_models()
        resolved = _pick_model(configured, available)
        self._resolved_model_cache = (now, resolved)
        if available and resolved != configured:
            logger.info(
                "LM Studio model resolved | configured=%r | using=%r | available=%s",
                configured,
                resolved,
                available[:8],
            )
        return resolved

    def healthcheck(self) -> dict[str, Any]:
        base = self.base_url
        configured = self.model_name
        if not base:
            return {
                "status": "offline",
                "detail": (
                    "LM Studio endpoint is not configured. "
                    "Set LM_STUDIO_ENDPOINT or enter a URL in AI Settings."
                ),
                "provider": self.name,
                "model": configured,
                "available_models": [],
                "endpoint": "",
            }
        started = time.perf_counter()
        try:
            available = self._list_available_models()
            latency_ms = (time.perf_counter() - started) * 1000.0
            if not available:
                logger.warning(
                    "LMStudioProvider health: reachable but no models | "
                    "endpoint=%s | latency_ms=%.1f",
                    base,
                    latency_ms,
                )
                return {
                    "status": "error",
                    "detail": (
                        f"LM Studio is reachable at {base}, but no models are loaded. "
                        "Load a model in LM Studio, then retry."
                    ),
                    "provider": self.name,
                    "model": configured,
                    "available_models": [],
                    "endpoint": base,
                    "latency_ms": round(latency_ms, 2),
                }

            resolved = self.resolve_model(force_refresh=True)
            auto = configured.strip().lower() in _AUTO_MODEL_TOKENS
            detail = (
                f"LM Studio reachable at {base}. Using loaded model '{resolved}'."
                if auto or resolved != configured
                else f"LM Studio reachable at {base}"
            )
            logger.info(
                "LMStudioProvider health online | endpoint=%s | model=%s | latency_ms=%.1f",
                base,
                resolved,
                latency_ms,
            )
            return {
                "status": "connected",
                "detail": detail,
                "provider": self.name,
                "model": resolved,
                "configured_model": configured,
                "available_models": available[:20],
                "endpoint": base,
                "latency_ms": round(latency_ms, 2),
            }
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.perf_counter() - started) * 1000.0
            logger.warning(
                "LMStudioProvider health failed | endpoint=%s | error=%s | latency_ms=%.1f",
                base,
                type(exc).__name__,
                latency_ms,
            )
            return {
                "status": "offline",
                "detail": _OFFLINE_MSG,
                "provider": self.name,
                "model": configured,
                "endpoint": base,
                "latency_ms": round(latency_ms, 2),
            }

    def available_models(self) -> list[str]:
        try:
            return self._list_available_models()
        except Exception:  # noqa: BLE001
            return []

    def _auth_headers(self) -> dict[str, str]:
        """
        Authorization for OpenAI-compatible endpoints (never logged).

        When ``LM_STUDIO_API_KEY`` is set, every request sends
        ``Authorization: Bearer <token>``. When unset, omit the header so
        open LAN / local servers still work.
        """
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    def _list_available_models(self) -> list[str]:
        base = self._require_endpoint()
        models = self._get_json(f"{base}/models", timeout=self._health_timeout)
        available: list[str] = []
        if isinstance(models, dict) and isinstance(models.get("data"), list):
            for item in models["data"]:
                if isinstance(item, dict) and item.get("id"):
                    mid = str(item["id"]).strip()
                    if mid:
                        available.append(mid)
        return available

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        raw = self._request_bytes(
            url,
            method="POST",
            body=body,
            headers={
                "Content-Type": "application/json",
                **self._auth_headers(),
            },
            timeout=self._timeout,
            retryable=True,
        )
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("LM Studio returned a non-object JSON payload")
        return data

    def _post_sse_deltas(self, url: str, payload: dict[str, Any]) -> Iterator[str]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                **self._auth_headers(),
                "Accept": "text/event-stream",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                while True:
                    raw_line = resp.readline()
                    if not raw_line:
                        break
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = _extract_stream_delta(event)
                    if delta:
                        yield delta
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(_friendly_lm_http_error(exc.code, detail)) from exc
        except TimeoutError as exc:
            logger.warning("LMStudioProvider stream timeout | url_host=%s", _safe_host(url))
            raise RuntimeError("Local AI server timed out. Please try again.") from exc
        except urllib.error.URLError as exc:
            logger.warning(
                "LMStudioProvider stream offline | url_host=%s | error=%s",
                _safe_host(url),
                type(exc).__name__,
            )
            raise RuntimeError(_OFFLINE_MSG) from exc

    def _get_json(self, url: str, *, timeout: float | None = None) -> Any:
        raw = self._request_bytes(
            url,
            method="GET",
            body=None,
            headers=self._auth_headers(),
            timeout=timeout if timeout is not None else min(self._timeout, 10.0),
            retryable=True,
        )
        return json.loads(raw.decode("utf-8"))

    def _request_bytes(
        self,
        url: str,
        *,
        method: str,
        body: bytes | None,
        headers: dict[str, str],
        timeout: float,
        retryable: bool,
    ) -> bytes:
        """HTTP/HTTPS request with optional retries (never logs secrets or bodies)."""
        attempts = 1 + (self._max_retries if retryable else 0)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            req = urllib.request.Request(
                url,
                data=body,
                method=method,
                headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                latency_ms = (time.perf_counter() - started) * 1000.0
                if attempt > 1:
                    logger.info(
                        "LMStudioProvider request recovered | method=%s | host=%s | "
                        "attempt=%s | latency_ms=%.1f",
                        method,
                        _safe_host(url),
                        attempt,
                        latency_ms,
                    )
                return raw
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                # Retry transient server / gateway failures only.
                if retryable and exc.code in {408, 429, 500, 502, 503, 504} and attempt < attempts:
                    logger.warning(
                        "LMStudioProvider HTTP %s — retrying | method=%s | host=%s | "
                        "attempt=%s/%s",
                        exc.code,
                        method,
                        _safe_host(url),
                        attempt,
                        attempts,
                    )
                    time.sleep(min(0.5 * attempt, 2.0))
                    last_error = RuntimeError(_friendly_lm_http_error(exc.code, detail))
                    continue
                raise RuntimeError(_friendly_lm_http_error(exc.code, detail)) from exc
            except TimeoutError as exc:
                logger.warning(
                    "LMStudioProvider timeout | method=%s | host=%s | attempt=%s/%s",
                    method,
                    _safe_host(url),
                    attempt,
                    attempts,
                )
                last_error = RuntimeError("Local AI server timed out. Please try again.")
                if retryable and attempt < attempts:
                    time.sleep(min(0.5 * attempt, 2.0))
                    continue
                raise last_error from exc
            except urllib.error.URLError as exc:
                # URLError may wrap socket.timeout on some platforms.
                reason = getattr(exc, "reason", None)
                is_timeout = isinstance(reason, TimeoutError) or (
                    reason is not None and "timed out" in str(reason).lower()
                )
                if is_timeout:
                    logger.warning(
                        "LMStudioProvider timeout | method=%s | host=%s | attempt=%s/%s",
                        method,
                        _safe_host(url),
                        attempt,
                        attempts,
                    )
                    last_error = RuntimeError("Local AI server timed out. Please try again.")
                else:
                    logger.warning(
                        "LMStudioProvider offline | method=%s | host=%s | attempt=%s/%s | "
                        "error=%s",
                        method,
                        _safe_host(url),
                        attempt,
                        attempts,
                        type(exc).__name__,
                    )
                    last_error = RuntimeError(_OFFLINE_MSG)
                if retryable and attempt < attempts:
                    time.sleep(min(0.5 * attempt, 2.0))
                    continue
                raise last_error from exc
        if last_error:
            raise last_error
        raise RuntimeError(_OFFLINE_MSG)


def _safe_host(url: str) -> str:
    """Host-only fragment for logs (no query strings / credentials)."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return parsed.netloc or "(unknown)"
    except Exception:  # noqa: BLE001
        return "(unknown)"


def _friendly_lm_http_error(code: int, detail: str) -> str:
    lower = (detail or "").lower()
    if code in {401, 403}:
        return "Local AI server rejected the request (authorization failed)."
    if code == 429:
        return "Local AI server rate limit reached. Please try again shortly."
    if code >= 500:
        return "Local AI server error. Please try again."
    if "timeout" in lower:
        return "Local AI server timed out. Please try again."
    return f"Local AI request failed (HTTP {code})."


def _pick_model(configured: str, available: list[str]) -> str:
    """Choose the best model id for the current LM Studio session."""
    configured = (configured or "").strip()
    if not available:
        return configured or "local-model"

    if configured.lower() in _AUTO_MODEL_TOKENS:
        return available[0]

    if configured in available:
        return configured

    # Fuzzy match: path vs bare name (e.g. qwen3-8b vs qwen/qwen3-8b).
    norm_cfg = _normalize_model_id(configured)
    for mid in available:
        norm_mid = _normalize_model_id(mid)
        if (
            norm_cfg == norm_mid
            or norm_cfg in norm_mid
            or norm_mid in norm_cfg
            or configured.lower() in mid.lower()
            or mid.lower() in configured.lower()
        ):
            return mid

    return available[0]


def _normalize_model_id(model_id: str) -> str:
    text = (model_id or "").strip().lower().replace("\\", "/")
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    return text.replace("_", "-").replace(" ", "")


def _build_messages(
    system_prompt: str,
    history: Sequence[dict[str, str]] | None,
    user_prompt: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history_as_chat_messages(history))
    messages.append({"role": "user", "content": user_prompt})
    return messages


def _extract_message_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        if message_has_tool_calls(message):
            return json.dumps(
                {
                    "name": "tool_call",
                    "parameters": message.get("tool_calls") or message.get("function_call"),
                }
            )
        if message.get("content"):
            return str(message["content"])
    if first.get("text"):
        return str(first["text"])
    return ""


def _extract_stream_delta(event: dict[str, Any]) -> str:
    choices = event.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    delta = first.get("delta")
    if isinstance(delta, dict) and delta.get("content"):
        return str(delta["content"])
    message = first.get("message")
    if isinstance(message, dict) and message.get("content"):
        return str(message["content"])
    if first.get("text"):
        return str(first["text"])
    return ""


def _usage_int(usage: Any, key: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
