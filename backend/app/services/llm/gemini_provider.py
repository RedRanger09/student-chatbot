"""Google Gemini generation provider (grounded + general knowledge)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any, Sequence

from config.settings import get_settings
from backend.app.services.llm.base import LLMProvider, LLMResponse
from backend.app.services.llm.prompts import (
    GENERAL_KNOWLEDGE_SYSTEM_PROMPT,
    GROUNDING_SYSTEM_PROMPT,
    build_general_user_prompt,
    build_user_prompt,
    history_as_chat_messages,
)
from backend.app.services.runtime_config import get_runtime_llm_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GeminiProvider(LLMProvider):
    """Gemini-backed generator (grounded RAG or general educational)."""

    name = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        *,
        key_source: str = "server",
    ) -> None:
        """
        Args:
            api_key: Explicit key. When omitted and ``key_source`` is server,
                the optional server ``GOOGLE_API_KEY`` is used.
            model_name: Override Gemini model id.
            key_source: ``user`` | ``server`` (for metadata only — never logged with the key).
        """
        settings = get_settings()
        cfg = get_runtime_llm_config()
        if api_key is not None:
            self._api_key = (api_key or "").strip() or None
        elif key_source == "server":
            self._api_key = settings.google_api_key
        else:
            self._api_key = None
        self._key_source = key_source
        self._model_name = model_name or cfg.gemini_model
        self._model: Any | None = None

    @property
    def model_name(self) -> str:
        cfg = get_runtime_llm_config()
        return self._model_name or cfg.gemini_model

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def generate(
        self,
        context: str,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> LLMResponse:
        return self._run(
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
        return self._run(
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
        yield from self._stream(
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
        yield from self._stream(
            system_prompt=GENERAL_KNOWLEDGE_SYSTEM_PROMPT,
            user_prompt=build_general_user_prompt(question=question, history=history),
            history=history,
            log_label="generate_general_stream",
            context_chars=0,
        )

    def _run(
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
        model_name = self.model_name

        if not self._api_key:
            raise RuntimeError("No Gemini API key configured.")

        model = self._ensure_model(
            model_name,
            cfg.temperature,
            cfg.max_tokens,
            system_prompt=system_prompt,
        )
        contents = _build_gemini_contents(history, user_prompt)
        logger.info(
            "GeminiProvider %s | model=%s | key_source=%s | context_chars=%s | "
            "prompt_chars=%s | history=%s",
            log_label,
            model_name,
            self._key_source,
            context_chars,
            len(user_prompt),
            len(history or []),
        )
        try:
            response = model.generate_content(contents, stream=stream)
        except Exception as exc:  # noqa: BLE001
            raise _friendly_gemini_error(exc) from exc
        if stream:
            # Should not happen for _run; streaming uses _stream.
            parts: list[str] = []
            for chunk in response:
                piece = _extract_text(chunk)
                if piece:
                    parts.append(piece)
            text = "".join(parts)
            usage = {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
        else:
            text = _extract_text(response)
            usage = _extract_usage(response)

        if not text.strip():
            raise RuntimeError("Gemini returned an empty generation response")

        latency_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "GeminiProvider complete | mode=%s | model=%s | latency_ms=%.2f | tokens=%s",
            log_label,
            model_name,
            latency_ms,
            usage.get("total_tokens"),
        )
        return LLMResponse(
            content=text.strip(),
            provider=self.name,
            model=model_name,
            latency_ms=latency_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            raw={"usage": usage, "mode": log_label},
        )

    def _stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        history: Sequence[dict[str, str]] | None,
        log_label: str,
        context_chars: int,
    ) -> Iterator[str]:
        cfg = get_runtime_llm_config()
        model_name = self.model_name
        if not self._api_key:
            raise RuntimeError("No Gemini API key configured.")

        model = self._ensure_model(
            model_name,
            cfg.temperature,
            cfg.max_tokens,
            system_prompt=system_prompt,
        )
        contents = _build_gemini_contents(history, user_prompt)
        logger.info(
            "GeminiProvider %s | model=%s | key_source=%s | context_chars=%s | history=%s",
            log_label,
            model_name,
            self._key_source,
            context_chars,
            len(history or []),
        )
        try:
            response = model.generate_content(contents, stream=True)
        except Exception as exc:  # noqa: BLE001
            raise _friendly_gemini_error(exc) from exc
        for chunk in response:
            piece = _extract_text(chunk)
            if piece:
                yield piece

    def healthcheck(self) -> dict[str, Any]:
        if not self._api_key:
            return {
                "status": "missing_api_key",
                "detail": "No Gemini API key configured.",
                "provider": self.name,
                "model": self.model_name,
                "key_source": self._key_source,
            }
        try:
            self._ensure_model(
                self.model_name,
                0.0,
                16,
                system_prompt=GROUNDING_SYSTEM_PROMPT,
            )
            return {
                "status": "connected",
                "detail": f"Gemini model '{self.model_name}' is configured",
                "provider": self.name,
                "model": self.model_name,
                "key_source": self._key_source,
            }
        except Exception as exc:  # noqa: BLE001
            # Never include credential material in logs.
            logger.error("Gemini healthcheck failed | key_source=%s | error=%s", self._key_source, exc)
            return {
                "status": "error",
                "detail": str(_friendly_gemini_error(exc)),
                "provider": self.name,
                "model": self.model_name,
                "key_source": self._key_source,
            }

    def available_models(self) -> list[str]:
        return [self.model_name] if self.model_name else []

    def validate_api_key(self) -> dict[str, Any]:
        """
        Lightweight live validation of the configured key.

        Does not persist the key. Never logs the key value.
        """
        if not self._api_key:
            return {
                "valid": False,
                "status": "missing_api_key",
                "detail": "No Gemini API key configured.",
                "provider": self.name,
                "model": self.model_name,
            }
        try:
            import google.generativeai as genai

            genai.configure(api_key=self._api_key)
            # Listing models is a cheap authenticated call.
            models = list(genai.list_models())
            if not models:
                return {
                    "valid": False,
                    "status": "error",
                    "detail": "Invalid API key",
                    "provider": self.name,
                    "model": self.model_name,
                }
            return {
                "valid": True,
                "status": "connected",
                "detail": "Gemini API key verified",
                "provider": self.name,
                "model": self.model_name,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini key validation failed | key_source=%s", self._key_source)
            return {
                "valid": False,
                "status": "error",
                "detail": "Invalid API key",
                "provider": self.name,
                "model": self.model_name,
                "error_class": type(exc).__name__,
            }

    def _ensure_model(
        self,
        model_name: str,
        temperature: float,
        max_tokens: int,
        *,
        system_prompt: str,
    ) -> Any:
        import google.generativeai as genai

        genai.configure(api_key=self._api_key)
        self._model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_prompt,
            generation_config={
                "temperature": float(temperature),
                "max_output_tokens": int(max_tokens),
            },
        )
        return self._model


def _build_gemini_contents(
    history: Sequence[dict[str, str]] | None,
    user_prompt: str,
) -> list[dict[str, Any]] | str:
    """
    Prefer native multi-turn contents when history exists.

    History turns are sent as prior roles; the final user turn carries the
    current CONTEXT/QUESTION prompt (which still includes a compact history
    block for models that benefit from explicit RECENT CONVERSATION text).
    """
    prior = history_as_chat_messages(history)
    if not prior:
        return user_prompt
    contents: list[dict[str, Any]] = []
    for turn in prior:
        role = "user" if turn["role"] == "user" else "model"
        contents.append({"role": role, "parts": [turn["content"]]})
    contents.append({"role": "user", "parts": [user_prompt]})
    return contents


def _extract_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text)
    parts: list[str] = []
    for cand in getattr(response, "candidates", []) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", []) or []:
            piece = getattr(part, "text", None)
            if piece:
                parts.append(str(piece))
    return "".join(parts)


def _extract_usage(response: Any) -> dict[str, int | None]:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    return {
        "prompt_tokens": getattr(meta, "prompt_token_count", None),
        "completion_tokens": getattr(meta, "candidates_token_count", None),
        "total_tokens": getattr(meta, "total_token_count", None),
    }


def _friendly_gemini_error(exc: Exception) -> RuntimeError:
    """Map provider exceptions to clear, non-sensitive user messages."""
    text = str(exc) or type(exc).__name__
    lower = text.lower()
    if "api key" in lower or "api_key" in lower or "permission" in lower or "401" in lower:
        return RuntimeError("Invalid or expired Gemini API key.")
    if "429" in lower or "quota" in lower or "rate" in lower:
        return RuntimeError("Gemini rate limit reached. Please try again shortly.")
    if "timeout" in lower or "timed out" in lower:
        return RuntimeError("Gemini request timed out. Please try again.")
    if "connect" in lower or "network" in lower or "unreachable" in lower:
        return RuntimeError("Could not reach Gemini. Check your network connection.")
    # Avoid leaking raw upstream payloads that might echo credentials.
    return RuntimeError("Gemini request failed. Please verify your API key and try again.")
