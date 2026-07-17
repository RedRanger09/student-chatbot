"""
Escalation Manager — maps sensitive messages to support resources.

Does not generate answers. Does not call LLMs. Deterministic only.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from src.utils.logger import get_logger

logger = get_logger(__name__)

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

EscalationCategory = Literal[
    "mental_health_crisis",
    "self_harm_suicide",
    "harassment",
    "bullying",
    "sexual_harassment",
    "discrimination",
    "medical_emergency",
    "campus_safety",
    "legal_issues",
    "violence_threats",
    "academic_misconduct",
    "unknown_sensitive",
    "general_complaint",
]

CATEGORY_LABELS: dict[str, str] = {
    "mental_health_crisis": "Mental Health Crisis",
    "self_harm_suicide": "Self-harm / Suicide",
    "harassment": "Harassment",
    "bullying": "Bullying",
    "sexual_harassment": "Sexual Harassment",
    "discrimination": "Discrimination",
    "medical_emergency": "Medical Emergency",
    "campus_safety": "Campus Safety",
    "legal_issues": "Legal Issues",
    "violence_threats": "Violence / Threats",
    "academic_misconduct": "Academic Misconduct Reports",
    "unknown_sensitive": "Unknown Sensitive Situation",
    "general_complaint": "General Complaint",
}

_CONTACTS_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "support_contacts.json"
)

# Ordered by priority (highest first) so CRITICAL patterns win.
_CATEGORY_RULES: list[tuple[str, Severity, tuple[str, ...]]] = [
    (
        "self_harm_suicide",
        "CRITICAL",
        (
            r"\bkill myself\b",
            r"\bsuicide\b",
            r"\bsuicidal\b",
            r"\bend my life\b",
            r"\btake my (own )?life\b",
            r"\bself[- ]?harm\b",
            r"\bhurt myself\b",
            r"\bharm myself\b",
            r"\bwant to harm myself\b",
            r"\bcut myself\b",
            r"\bwant to die\b",
            r"\bdon't want to (live|be alive)\b",
            r"\bdont want to (live|be alive)\b",
        ),
    ),
    (
        "violence_threats",
        "CRITICAL",
        (
            r"\b(i will|i'll|im going to|i am going to)\s+(kill|hurt|attack|stab|shoot)\b",
            r"\bbomb threat\b",
            r"\bbring a (gun|weapon|knife)\b",
            r"\bthreat(en|ening)?\s+(to )?(kill|hurt|harm)\b",
            r"\bhow\s+(can|do|to)\s+(i|you|we)\s+(make|build|create|assemble)\s+(a\s+)?(bomb|explosive|ied)\b",
            r"\b(make|build|create|assemble)\s+(a\s+)?(bomb|explosive|ied)\b",
            r"\bbomb\s+(making|recipe|instructions|tutorial)\b",
            r"\b(pipe\s+bomb|molotov)\b",
        ),
    ),
    (
        "medical_emergency",
        "HIGH",
        (
            r"\bmedical emergency\b",
            r"\bneed a doctor (now|urgently|immediately)\b",
            r"\bchest pain\b",
            r"\bcan't breathe\b",
            r"\bcannot breathe\b",
            r"\bpassing out\b",
            r"\bunconscious\b",
            r"\boverdose\b",
            r"\bsevere bleeding\b",
            r"\bambulance\b",
        ),
    ),
    (
        "campus_safety",
        "HIGH",
        (
            r"\bfeel unsafe\b",
            r"\bfelt unsafe\b",
            r"\bunsafe on campus\b",
            r"\bstalk(ing|er)?\b",
            r"\bfollowed (me|home)\b",
            r"\bbroke into\b",
            r"\bintruder\b",
        ),
    ),
    (
        "sexual_harassment",
        "HIGH",
        (
            r"\bsexual harassment\b",
            r"\bsexually harass(ed|ing)?\b",
            r"\bmolest(ed|ation)?\b",
            r"\bassault(ed)?\b",
            r"\brape\b",
            r"\binappropriate touch(ing)?\b",
        ),
    ),
    (
        "mental_health_crisis",
        "HIGH",
        (
            r"\bdepressed\b",
            r"\bdepression\b",
            r"\banxiety attack\b",
            r"\bpanic attack\b",
            r"\bmental (health )?crisis\b",
            r"\bi (can't|cannot) cope\b",
            r"\bhaving a breakdown\b",
            r"\bhopeless\b",
        ),
    ),
    (
        "harassment",
        "MEDIUM",
        (
            r"\bharass(ed|ing|ment)?\b",
            r"\bintimidate(d|ing)?\b",
            r"\bhostile environment\b",
        ),
    ),
    (
        "bullying",
        "MEDIUM",
        (
            r"\bbully(ing|ied)?\b",
            r"\bragg(ing|ed)?\b",
            r"\bcycl?e of abuse\b",
        ),
    ),
    (
        "discrimination",
        "MEDIUM",
        (
            r"\bdiscriminat(e|ed|ion|ing)\b",
            r"\bracis(t|m)\b",
            r"\bcaste (abuse|discrimination)\b",
            r"\bgender bias\b",
        ),
    ),
    (
        "legal_issues",
        "MEDIUM",
        (
            r"\blegal (threat|action|notice|case)\b",
            r"\blawsuit\b",
            r"\bpolice complaint\b",
            r"\bfir\b",
            r"\blawyer\b",
            r"\battorney\b",
        ),
    ),
    (
        "academic_misconduct",
        "MEDIUM",
        (
            r"\bcheating (incident|report|case)\b",
            r"\bplagiarism (report|complaint)\b",
            r"\bacademic misconduct\b",
            r"\bmalpractice (report|complaint)\b",
            r"\breport(ing)? (someone for )?cheating\b",
        ),
    ),
    (
        "general_complaint",
        "LOW",
        (
            r"\bfile a complaint\b",
            r"\bwanna complain\b",
            r"\bwant to complain\b",
            r"\bgrievance\b",
        ),
    ),
]


@dataclass(frozen=True)
class ContactResource:
    """Configured institutional support contact."""

    id: str
    name: str
    office: str
    email: str
    phone: str
    office_hours: str
    emergency_notice: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EscalationDecision:
    """Structured escalation outcome for the Safety Layer."""

    category: str
    severity: Severity
    contact_resource: ContactResource
    requires_ticket: bool
    allow_generation: bool
    category_label: str = ""
    matched_signals: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "category_label": self.category_label or CATEGORY_LABELS.get(self.category, self.category),
            "severity": self.severity,
            "contact_resource": self.contact_resource.to_dict(),
            "requires_ticket": self.requires_ticket,
            "allow_generation": self.allow_generation,
            "matched_signals": list(self.matched_signals),
            "reason": self.reason,
        }


class EscalationManager:
    """Determine escalation category, severity, and contact resource."""

    def __init__(self, contacts_path: Path | None = None) -> None:
        self._contacts_path = Path(contacts_path) if contacts_path else _CONTACTS_PATH
        self._resources, self._category_defaults = self._load_contacts()

    def evaluate(
        self,
        message: str,
        *,
        intent: str | None = None,
        forced_category: str | None = None,
    ) -> EscalationDecision | None:
        """
        Return an ``EscalationDecision`` when escalation is required.

        Returns ``None`` when generation may proceed.
        """
        text = (message or "").strip()
        category: str | None = forced_category
        severity: Severity | None = None
        matched: list[str] = []

        if category is None:
            detected = self._detect_category(text)
            if detected is not None:
                category, severity, matched = detected

        if category is None and intent == "escalate":
            category = "unknown_sensitive"
            severity = "MEDIUM"
            matched = ["intent_router:escalate"]

        if category is None:
            return None

        severity = severity or self._default_severity(category)
        resource = self._resolve_resource(category)
        requires_ticket = severity in {"MEDIUM", "HIGH", "CRITICAL"}
        decision = EscalationDecision(
            category=category,
            severity=severity,
            contact_resource=resource,
            requires_ticket=requires_ticket,
            allow_generation=False,
            category_label=CATEGORY_LABELS.get(category, category),
            matched_signals=matched,
            reason="deterministic_escalation",
        )
        logger.info(
            "EscalationManager decision | category=%s | severity=%s | "
            "resource=%s | requires_ticket=%s | signals=%s",
            decision.category,
            decision.severity,
            decision.contact_resource.id,
            decision.requires_ticket,
            decision.matched_signals[:5],
        )
        return decision

    def get_resource(self, resource_id: str) -> ContactResource:
        if resource_id in self._resources:
            return self._resources[resource_id]
        return self._fallback_resource()

    def _detect_category(
        self,
        text: str,
    ) -> tuple[str, Severity, list[str]] | None:
        if not text:
            return None
        for category, severity, patterns in _CATEGORY_RULES:
            hits: list[str] = []
            for pattern in patterns:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    hits.append(pattern)
            if hits:
                return category, severity, hits
        return None

    def _resolve_resource(self, category: str) -> ContactResource:
        resource_id = self._category_defaults.get(category, "student_affairs")
        if resource_id in self._resources:
            return self._resources[resource_id]
        logger.warning(
            "EscalationManager missing resource %s for category %s — using fallback",
            resource_id,
            category,
        )
        return self._fallback_resource()

    @staticmethod
    def _default_severity(category: str) -> Severity:
        mapping: dict[str, Severity] = {
            "self_harm_suicide": "CRITICAL",
            "violence_threats": "CRITICAL",
            "medical_emergency": "HIGH",
            "campus_safety": "HIGH",
            "sexual_harassment": "HIGH",
            "mental_health_crisis": "HIGH",
            "harassment": "MEDIUM",
            "bullying": "MEDIUM",
            "discrimination": "MEDIUM",
            "legal_issues": "MEDIUM",
            "academic_misconduct": "MEDIUM",
            "unknown_sensitive": "MEDIUM",
            "general_complaint": "LOW",
        }
        return mapping.get(category, "MEDIUM")

    def _load_contacts(self) -> tuple[dict[str, ContactResource], dict[str, str]]:
        if not self._contacts_path.exists():
            logger.error(
                "Support contacts file missing: %s — using built-in fallbacks",
                self._contacts_path,
            )
            fallback = self._fallback_resource()
            return {fallback.id: fallback}, {"unknown_sensitive": fallback.id}

        try:
            payload = json.loads(self._contacts_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to parse support contacts: %s", exc)
            fallback = self._fallback_resource()
            return {fallback.id: fallback}, {"unknown_sensitive": fallback.id}

        resources: dict[str, ContactResource] = {}
        for key, raw in (payload.get("resources") or {}).items():
            if not isinstance(raw, dict):
                continue
            resources[key] = ContactResource(
                id=str(raw.get("id") or key),
                name=str(raw.get("name") or key),
                office=str(raw.get("office") or "Campus office (placeholder)"),
                email=str(raw.get("email") or "support@college.edu"),
                phone=str(raw.get("phone") or "+91-XXXX-XXXXXX"),
                office_hours=str(raw.get("office_hours") or "Mon–Fri (placeholder)"),
                emergency_notice=raw.get("emergency_notice"),
            )
        defaults = {
            str(k): str(v)
            for k, v in (payload.get("category_defaults") or {}).items()
        }
        if not resources:
            fallback = self._fallback_resource()
            resources = {fallback.id: fallback}
        return resources, defaults

    @staticmethod
    def _fallback_resource() -> ContactResource:
        return ContactResource(
            id="student_affairs",
            name="Student Affairs Office",
            office="Administration Block (placeholder)",
            email="student.affairs@college.edu",
            phone="+91-XXXX-XXXXXX",
            office_hours="Mon–Fri, 9:00 AM – 5:00 PM",
            emergency_notice=(
                "If this is an emergency, contact campus security or local "
                "emergency services immediately."
            ),
        )


_escalation_manager: EscalationManager | None = None


def get_escalation_manager() -> EscalationManager:
    global _escalation_manager
    if _escalation_manager is None:
        _escalation_manager = EscalationManager()
    return _escalation_manager
