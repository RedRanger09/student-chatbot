"""
Safety Layer — deterministic guardrails before generation.

The LLM never decides safety. Blocked categories never reach providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.services.escalation_manager import (
    EscalationDecision,
    EscalationManager,
    get_escalation_manager,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SafetyDecision:
    """Outcome of the Safety Layer check."""

    allowed: bool
    safety_decision: str  # allowed | blocked_escalate
    generation_blocked: bool
    escalation: EscalationDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "safety_decision": self.safety_decision,
            "generation_blocked": self.generation_blocked,
            "escalation": self.escalation.to_dict() if self.escalation else None,
        }


class SafetyLayer:
    """
    Pre-generation guardrails.

    Runs after intent routing and before retrieval / generation paths that
    would call an LLM.
    """

    def __init__(self, escalation_manager: EscalationManager | None = None) -> None:
        self._escalation_manager = escalation_manager or get_escalation_manager()

    def check(self, message: str, *, intent: str | None = None) -> SafetyDecision:
        """
        Evaluate whether generation is allowed.

        Returns a blocked decision when escalation is required.
        """
        escalation = self._escalation_manager.evaluate(message, intent=intent)
        if escalation is None or escalation.allow_generation:
            decision = SafetyDecision(
                allowed=True,
                safety_decision="allowed",
                generation_blocked=False,
                escalation=None,
            )
            logger.info(
                "SafetyLayer decision | safety_decision=allowed | generation_blocked=false | "
                "intent=%s",
                intent,
            )
            return decision

        decision = SafetyDecision(
            allowed=False,
            safety_decision="blocked_escalate",
            generation_blocked=True,
            escalation=escalation,
        )
        logger.info(
            "SafetyLayer decision | safety_decision=blocked_escalate | "
            "generation_blocked=true | category=%s | severity=%s | intent=%s",
            escalation.category,
            escalation.severity,
            intent,
        )
        return decision


_safety_layer: SafetyLayer | None = None


def get_safety_layer() -> SafetyLayer:
    global _safety_layer
    if _safety_layer is None:
        _safety_layer = SafetyLayer()
    return _safety_layer
