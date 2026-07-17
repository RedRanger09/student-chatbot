"""
LLM Service — provider-agnostic generation entry point for ChatService.

ChatService calls this service only. It never imports Gemini or LM Studio.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from backend.app.services.context_builder import BuiltContext
from backend.app.services.llm.base import LLMResponse
from backend.app.services.llm.provider_factory import (
    ProviderFactory,
    ProviderOfflineError,
    ProviderUnavailableError,
    get_provider_factory,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class GenerationResult:
    """Outcome of a grounded generation attempt."""

    content: str
    provider: str | None
    model: str | None
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    selection: dict[str, Any]
    success: bool
    error: str | None = None


class LLMService:
    """Orchestrates provider selection + grounded generation."""

    def __init__(self, factory: ProviderFactory | None = None) -> None:
        self._factory = factory or get_provider_factory()

    def generate(
        self,
        *,
        context: BuiltContext,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> GenerationResult:
        """
        Generate a grounded markdown answer.

        If context is empty, returns a friendly insufficiency message without
        calling a provider.
        """
        started = time.perf_counter()
        if context.is_empty:
            logger.info("LLMService skipped generation — empty context")
            return GenerationResult(
                content=(
                    "I don't have enough retrieved context to answer that safely. "
                    "Please try rephrasing your question, or upload relevant notes "
                    "if you're asking about personal study material."
                ),
                provider=None,
                model=None,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                selection={"mode": "skipped", "reason": "empty_context"},
                success=True,
                error=None,
            )

        try:
            provider, selection = self._factory.select_provider()
        except ProviderOfflineError as exc:
            logger.warning("LLMService provider offline: %s", exc)
            return self._unavailable_result(started, exc, mode="lmstudio_offline")
        except ProviderUnavailableError as exc:
            logger.error("LLMService provider selection failed: %s", exc)
            return self._unavailable_result(started, exc, mode="auto")

        try:
            logger.info(
                "LLMService generate | provider=%s | context_chars=%s | "
                "prompt_sources=%s | history=%s",
                provider.name,
                len(context.formatted_context),
                len(context.sources),
                len(history or []),
            )
            response: LLMResponse = provider.generate(
                context.formatted_context,
                question,
                history=history,
            )
            return self._from_response(response, selection)
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLMService generation failure via %s: %s", provider.name, exc)
            return GenerationResult(
                content=(
                    "I retrieved relevant information, but answer generation failed. "
                    f"({provider.name}: {exc})\n\n"
                    "Please verify your AI Settings connection and try again."
                ),
                provider=provider.name,
                model=self._provider_model(provider),
                latency_ms=(time.perf_counter() - started) * 1000.0,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                selection=selection,
                success=False,
                error=str(exc),
            )

    def generate_general(
        self,
        *,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> GenerationResult:
        """
        Generate a general educational answer without retrieved context.

        Used only after Hybrid Knowledge Mode classifies the query as
        ``general_ai``. Never invents campus-specific facts via prompt rules.
        """
        started = time.perf_counter()
        try:
            provider, selection = self._factory.select_provider()
        except ProviderOfflineError as exc:
            logger.warning("LLMService general provider offline: %s", exc)
            return self._unavailable_result(started, exc, mode="lmstudio_offline")
        except ProviderUnavailableError as exc:
            logger.error("LLMService general provider selection failed: %s", exc)
            return self._unavailable_result(started, exc, mode="general_ai")

        try:
            logger.info(
                "LLMService generate_general | provider=%s | question_chars=%s | history=%s",
                provider.name,
                len(question or ""),
                len(history or []),
            )
            response = provider.generate_general(question, history=history)
            selection = {**selection, "knowledge_mode": "general_ai", "fallback": True}
            return self._from_response(response, selection)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "LLMService general generation failure via %s: %s",
                provider.name,
                exc,
            )
            return GenerationResult(
                content=(
                    "I couldn't generate a general-knowledge answer right now. "
                    f"({provider.name}: {exc})\n\n"
                    "Please verify your AI Settings connection and try again."
                ),
                provider=provider.name,
                model=self._provider_model(provider),
                latency_ms=(time.perf_counter() - started) * 1000.0,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                selection={**selection, "knowledge_mode": "general_ai"},
                success=False,
                error=str(exc),
            )

    def generate_stream(
        self,
        *,
        context: BuiltContext,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> Iterator[str | GenerationResult]:
        """
        Stream grounded answer deltas, then yield a final ``GenerationResult``.

        Yields ``str`` token chunks, followed by one ``GenerationResult``.
        """
        started = time.perf_counter()
        if context.is_empty:
            result = self.generate(context=context, question=question, history=history)
            if result.content:
                yield result.content
            yield result
            return

        try:
            provider, selection = self._factory.select_provider()
        except ProviderOfflineError as exc:
            result = self._unavailable_result(started, exc, mode="lmstudio_offline")
            if result.content:
                yield result.content
            yield result
            return
        except ProviderUnavailableError as exc:
            result = self._unavailable_result(started, exc, mode="auto")
            if result.content:
                yield result.content
            yield result
            return

        parts: list[str] = []
        try:
            logger.info(
                "LLMService generate_stream | provider=%s | history=%s",
                provider.name,
                len(history or []),
            )
            for delta in provider.generate_stream(
                context.formatted_context,
                question,
                history=history,
            ):
                if not delta:
                    continue
                parts.append(delta)
                yield delta
            content = "".join(parts).strip()
            if not content:
                raise RuntimeError("Provider returned an empty streamed response")
            yield GenerationResult(
                content=content,
                provider=provider.name,
                model=self._provider_model(provider),
                latency_ms=(time.perf_counter() - started) * 1000.0,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                selection=selection,
                success=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLMService stream failure via %s: %s", provider.name, exc)
            partial = "".join(parts).strip()
            message = (
                partial
                or (
                    "I retrieved relevant information, but answer generation failed. "
                    f"({provider.name}: {exc})\n\n"
                    "Please verify your AI Settings connection and try again."
                )
            )
            if not partial and message:
                yield message
            yield GenerationResult(
                content=message,
                provider=provider.name,
                model=self._provider_model(provider),
                latency_ms=(time.perf_counter() - started) * 1000.0,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                selection=selection,
                success=False,
                error=str(exc),
            )

    def generate_general_stream(
        self,
        *,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> Iterator[str | GenerationResult]:
        """Stream general-knowledge deltas, then yield a final ``GenerationResult``."""
        started = time.perf_counter()
        try:
            provider, selection = self._factory.select_provider()
        except ProviderOfflineError as exc:
            result = self._unavailable_result(started, exc, mode="lmstudio_offline")
            if result.content:
                yield result.content
            yield result
            return
        except ProviderUnavailableError as exc:
            result = self._unavailable_result(started, exc, mode="general_ai")
            if result.content:
                yield result.content
            yield result
            return

        parts: list[str] = []
        selection = {**selection, "knowledge_mode": "general_ai", "fallback": True}
        try:
            logger.info(
                "LLMService generate_general_stream | provider=%s | history=%s",
                provider.name,
                len(history or []),
            )
            for delta in provider.generate_general_stream(question, history=history):
                if not delta:
                    continue
                parts.append(delta)
                yield delta
            content = "".join(parts).strip()
            if not content:
                raise RuntimeError("Provider returned an empty streamed response")
            yield GenerationResult(
                content=content,
                provider=provider.name,
                model=self._provider_model(provider),
                latency_ms=(time.perf_counter() - started) * 1000.0,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                selection=selection,
                success=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "LLMService general stream failure via %s: %s", provider.name, exc
            )
            partial = "".join(parts).strip()
            message = (
                partial
                or (
                    "I couldn't generate a general-knowledge answer right now. "
                    f"({provider.name}: {exc})\n\n"
                    "Please verify your AI Settings connection and try again."
                )
            )
            if not partial and message:
                yield message
            yield GenerationResult(
                content=message,
                provider=provider.name,
                model=self._provider_model(provider),
                latency_ms=(time.perf_counter() - started) * 1000.0,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                selection=selection,
                success=False,
                error=str(exc),
            )

    @staticmethod
    def _from_response(response: LLMResponse, selection: dict[str, Any]) -> GenerationResult:
        return GenerationResult(
            content=response.content,
            provider=response.provider,
            model=response.model,
            latency_ms=response.latency_ms,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            selection=selection,
            success=True,
        )

    @staticmethod
    def _provider_model(provider: Any) -> str | None:
        """Return the answering model id (resolved for LM Studio when possible)."""
        resolve = getattr(provider, "resolve_model", None)
        if callable(resolve):
            try:
                resolved = resolve()
                if resolved:
                    return str(resolved)
            except Exception:  # noqa: BLE001
                pass
        name = getattr(provider, "model_name", None)
        return str(name) if name else None

    @staticmethod
    def _unavailable_result(
        started: float,
        exc: Exception,
        *,
        mode: str,
    ) -> GenerationResult:
        if mode == "lmstudio_offline":
            content = "Local AI server is currently offline."
        elif mode == "general_ai":
            content = (
                "I'd like to explain that from general knowledge, but no AI provider "
                "is available right now.\n\n"
                "Add your Gemini API key in AI Settings, or wait until the local AI "
                "endpoint is online, then try again."
            )
        else:
            message = str(exc) if str(exc).strip() else "No AI provider available."
            if "No Gemini API key" in message:
                content = (
                    "No Gemini API key configured.\n\n"
                    "Add your own key in AI Settings (stored only in this browser), "
                    "or switch to Auto / LM Studio when the local endpoint is online."
                )
            elif "No AI provider" in message:
                content = (
                    "No AI provider available.\n\n"
                    "- Wait until the configured LM Studio endpoint is online, **or**\n"
                    "- Add your Gemini API key in AI Settings (browser only).\n\n"
                    "Then try your question again."
                )
            else:
                content = message
        return GenerationResult(
            content=content,
            provider=None,
            model=None,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            selection={"mode": mode, "error": str(exc)},
            success=False,
            error=str(exc),
        )


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
