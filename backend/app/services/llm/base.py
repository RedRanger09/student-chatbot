"""Shared LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass(frozen=True)
class LLMResponse:
    """Normalized generation result from any provider."""

    content: str
    provider: str
    model: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.content and self.content.strip())


class LLMProvider(ABC):
    """
    Provider contract used by the LLM service.

    ChatService never depends on a concrete provider class.
    Concrete providers implement generate / health / available_models.
    """

    name: str

    @abstractmethod
    def generate(
        self,
        context: str,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> LLMResponse:
        """Produce a grounded markdown answer from ``context`` + ``question``."""

    @abstractmethod
    def generate_general(
        self,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> LLMResponse:
        """Produce a general-knowledge educational answer (no retrieved context)."""

    def generate_stream(
        self,
        context: str,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> Iterator[str]:
        """
        Yield grounded answer text deltas.

        Default falls back to a single full-response chunk so callers can
        always use the streaming API surface.
        """
        response = self.generate(context, question, history=history)
        if response.content:
            yield response.content

    def generate_general_stream(
        self,
        question: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> Iterator[str]:
        """Yield general-knowledge answer text deltas."""
        response = self.generate_general(question, history=history)
        if response.content:
            yield response.content

    @abstractmethod
    def healthcheck(self) -> dict[str, Any]:
        """
        Return connection status for the Settings UI.

        Expected keys: status (connected|offline|missing_api_key|error), detail
        """

    def health(self) -> dict[str, Any]:
        """Alias for ``healthcheck`` (production provider interface)."""
        return self.healthcheck()

    def available_models(self) -> list[str]:
        """
        Return model ids the provider can use right now.

        Default: empty list. LM Studio overrides via ``/v1/models``.
        """
        return []
