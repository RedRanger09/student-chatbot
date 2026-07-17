"""
LLM-based Intent Router.

Responsibilities:
    - Normalize and score the user message
    - Classify into exactly one intent (Gemini when available)
    - Apply local confidence overrides for campus questions
    - Never answer the question / never retrieve documents
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from config.settings import get_settings
from backend.app.models.chat_models import VALID_INTENTS, ChatIntent, RouteDecision
from backend.app.services.intent_signals import (
    IntentScores,
    score_intents,
)
from backend.app.services.query_normalization import normalize_query
from src.utils.logger import get_logger

logger = get_logger(__name__)

ROUTER_SYSTEM_PROMPT = """You are the Intent Router for a Student Support Services AI Assistant.

Your ONLY job is to classify the user message into exactly ONE intent.
You must NOT answer the user's question.
You must NOT provide advice, facts, or explanations.
You must NOT retrieve documents.
Return JSON only — no markdown fences, no prose outside JSON.

Treat campus abbreviations and informal wording as institutional when relevant
(e.g. clg=college, marksheet=transcript, backlogs=failed subjects).

## Intents (choose exactly one)

### institutional_faq
Questions that can be answered from institutional / campus documents.
Examples:
- How much is the hostel fee?
- How do I apply for admission?
- What are the library timings? / clg library
- How do I register for exams?
- What scholarships are available?
- I cannot log into the ERP portal.
- When does the academic calendar start?
- How do I request a transcript or certificate / marksheet?
- What is the attendance requirement / attendance criteria?
- What are the important student policies I should know?
- Can I graduate if I still have backlogs?
- Hostel fees / parking policy / mess rules

### personal_notes
Questions about the student's own uploaded document / notes / syllabus / PDF.
Examples:
- Summarize my notes.
- Explain page 3 of my upload.
- According to my notes, what is overfitting?
- What does my uploaded syllabus say about grading?
- Quiz me on the document I uploaded.
If the message clearly refers to personal uploaded material, choose this intent
even if the topic sounds academic.

### escalate
Messages involving harm, crisis, or situations that need human support.
Examples:
- I feel depressed / I want to hurt myself
- Someone is harassing me
- I am being bullied / discriminated against
- Medical emergency / I need a doctor urgently
- Legal threat / I was assaulted
- I feel unsafe on campus
- How can I make a bomb?
NEVER answer these. Only classify as escalate.

### out_of_scope
Anything unrelated to campus institutional services or uploaded notes,
OR educational / academic study questions (e.g. explain ML, teach DSA),
OR lightweight helpful asks (movies, books, study tips, careers).
Educational and lightweight asks are classified out_of_scope here;
ChatService answers them via General AI — do NOT treat them as escalate.
Examples:
- What's the weather today?
- Who will win the election?
- Recommend a movie / book (ChatService may answer helpfully)
- Write Python code for a sorting algorithm (unless about campus ERP help)
- Who invented the telephone?
- Explain recursion / overfitting / machine learning (conceptual)
- Sports scores, celebrity gossip, general trivia
- Hi / How are you / Thanks (ChatService handles chit-chat)

## Edge cases
- "Hostel fee and also summarize my notes" → prefer institutional_faq if primarily
  campus policy; personal_notes if primarily about the upload. If equal, prefer
  personal_notes when "my notes/upload/document" is explicit.
- "When are exams and how can I improve recursion?" → institutional_faq
  (dominant campus intent is exams; conceptual half is secondary).
- Vague "help" with no topic → out_of_scope
- ERP / login / password reset for campus systems → institutional_faq
- Mental health wording that is clearly figurative and not about wellbeing
  (e.g. "this assignment is killing me") → institutional_faq or personal_notes
  as appropriate, NOT escalate — unless there is real self-harm / crisis language.
- Coding help for a programming course homework unrelated to campus services → out_of_scope
- Educational conceptual questions (e.g. "What is recursion?", "Explain overfitting",
  "What is machine learning?") → out_of_scope
  unless they ask for campus-specific policy.
- "How do I pay fees on the student portal?" → institutional_faq

## Output schema (JSON only)
{
  "intent": "institutional_faq" | "personal_notes" | "escalate" | "out_of_scope",
  "confidence": 0.0,
  "reason": "short justification",
  "requires_upload": false
}

Rules for requires_upload:
- Set true ONLY when intent is personal_notes AND no uploaded document is available.
- Otherwise false.

confidence must be a number between 0 and 1.
"""


class IntentRouter:
    """Gemini-backed classifier with local normalization + confidence overrides."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.google_api_key
        self._model_name = model_name or settings.gemini_model
        self._timeout_seconds = timeout_seconds
        self._model: Any | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def classify(
        self,
        query: str,
        *,
        has_uploaded_document: bool = False,
    ) -> RouteDecision:
        """
        Classify ``query`` into exactly one intent.

        Always normalizes and scores locally. Gemini (when available) proposes
        an intent; local institutional confidence can override weak
        ``out_of_scope`` decisions so campus FAQs still retrieve.
        """
        text = (query or "").strip()
        started = time.perf_counter()
        normalized = normalize_query(text)
        scores = score_intents(normalized or text)

        if not text:
            decision = self._fallback("empty_query")
            self._log_decision(
                text,
                decision,
                started,
                parse_ok=True,
                normalized=normalized,
                scores=scores,
            )
            return decision

        if not self._api_key:
            logger.error("IntentRouter: GOOGLE_API_KEY missing — using local scoring")
            decision = self._decision_from_scores(
                scores,
                reason="missing_api_key",
                has_uploaded_document=has_uploaded_document,
            )
            self._log_decision(
                text,
                decision,
                started,
                parse_ok=False,
                normalized=normalized,
                scores=scores,
            )
            return decision

        try:
            raw = self._call_gemini(
                text,
                normalized=normalized,
                has_uploaded_document=has_uploaded_document,
            )
            decision = self._parse_and_validate(
                raw,
                has_uploaded_document=has_uploaded_document,
            )
            decision = self._apply_local_overrides(
                decision,
                scores=scores,
                has_uploaded_document=has_uploaded_document,
            )
            self._log_decision(
                text,
                decision,
                started,
                parse_ok=True,
                normalized=normalized,
                scores=scores,
            )
            return decision
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "IntentRouter failure (%s): %s — using local scoring",
                type(exc).__name__,
                exc,
            )
            decision = self._decision_from_scores(
                scores,
                reason=f"error:{type(exc).__name__}",
                has_uploaded_document=has_uploaded_document,
            )
            self._log_decision(
                text,
                decision,
                started,
                parse_ok=False,
                normalized=normalized,
                scores=scores,
            )
            return decision

    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        import google.generativeai as genai

        genai.configure(api_key=self._api_key)
        self._model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=ROUTER_SYSTEM_PROMPT,
            generation_config={
                "temperature": 0.0,
                "response_mime_type": "application/json",
            },
        )
        logger.info("IntentRouter Gemini model ready: %s", self._model_name)
        return self._model

    def _call_gemini(
        self,
        query: str,
        *,
        normalized: str,
        has_uploaded_document: bool,
    ) -> str:
        model = self._ensure_model()
        upload_state = "yes" if has_uploaded_document else "no"
        user_prompt = (
            f"Uploaded document available: {upload_state}\n\n"
            f"User message:\n{query}\n\n"
            f"Normalized message (abbreviations expanded):\n{normalized or query}\n\n"
            "Classify the message. Return JSON only."
        )
        logger.info(
            "IntentRouter Gemini request | model=%s | upload=%s | query=%r | normalized=%r",
            self._model_name,
            upload_state,
            query[:200],
            (normalized or "")[:200],
        )

        response = model.generate_content(user_prompt)
        raw = getattr(response, "text", None) or ""
        if not raw and getattr(response, "candidates", None):
            parts: list[str] = []
            for cand in response.candidates:
                content = getattr(cand, "content", None)
                for part in getattr(content, "parts", []) or []:
                    piece = getattr(part, "text", None)
                    if piece:
                        parts.append(piece)
            raw = "".join(parts)
        if not raw.strip():
            raise ValueError("Empty Gemini classification response")
        return raw

    # ------------------------------------------------------------------
    # Validation + overrides
    # ------------------------------------------------------------------

    def _parse_and_validate(
        self,
        raw: str,
        *,
        has_uploaded_document: bool,
    ) -> RouteDecision:
        payload = _extract_json_object(raw)
        if payload is None:
            logger.error("IntentRouter JSON parsing failure | raw=%r", raw[:400])
            return self._fallback("invalid_json")

        intent_raw = str(payload.get("intent", "")).strip()
        if intent_raw not in VALID_INTENTS:
            logger.error("IntentRouter unknown intent %r — fallback", intent_raw)
            return self._fallback("unknown_intent")

        intent: ChatIntent = intent_raw  # type: ignore[assignment]

        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        reason = str(payload.get("reason", "")).strip() or "classified_by_gemini"

        requires_upload = bool(payload.get("requires_upload", False))
        if intent == "personal_notes" and not has_uploaded_document:
            requires_upload = True
        elif intent != "personal_notes":
            requires_upload = False
        else:
            requires_upload = False

        return RouteDecision(
            intent=intent,
            confidence=confidence,
            reason=reason,
            requires_upload=requires_upload,
        )

    def _apply_local_overrides(
        self,
        decision: RouteDecision,
        *,
        scores: IntentScores,
        has_uploaded_document: bool,
    ) -> RouteDecision:
        """Prefer institutional RAG when local campus confidence is strong."""
        if scores.escalate >= 0.75 and decision.intent != "escalate":
            return RouteDecision(
                intent="escalate",
                confidence=max(decision.confidence, scores.escalate),
                reason=f"{decision.reason}|override:local_escalate",
                requires_upload=False,
            )

        if scores.personal_notes >= 0.65 and decision.intent not in {
            "escalate",
            "personal_notes",
        }:
            return RouteDecision(
                intent="personal_notes",
                confidence=max(decision.confidence, scores.personal_notes),
                reason=f"{decision.reason}|override:local_personal_notes",
                requires_upload=not has_uploaded_document,
            )

        if decision.intent == "out_of_scope" and scores.institutional >= 0.42:
            if scores.educational >= scores.institutional + 0.25:
                return decision
            return RouteDecision(
                intent="institutional_faq",
                confidence=max(decision.confidence, scores.institutional),
                reason=(
                    f"{decision.reason}|override:local_institutional"
                    f":topics={','.join(scores.matched_topics) or 'signals'}"
                ),
                requires_upload=False,
            )

        # Low Gemini confidence + moderate campus signal → institutional.
        if (
            decision.intent == "out_of_scope"
            and decision.confidence < 0.55
            and scores.institutional >= 0.32
            and scores.institutional + 0.05 >= scores.educational
        ):
            return RouteDecision(
                intent="institutional_faq",
                confidence=max(decision.confidence, scores.institutional),
                reason=f"{decision.reason}|override:uncertain_institutional",
                requires_upload=False,
            )

        return decision

    def _decision_from_scores(
        self,
        scores: IntentScores,
        *,
        reason: str,
        has_uploaded_document: bool,
    ) -> RouteDecision:
        if scores.escalate >= 0.7:
            return RouteDecision(
                intent="escalate",
                confidence=scores.escalate,
                reason=f"local:{reason}:escalate",
                requires_upload=False,
            )
        if scores.personal_notes >= 0.55:
            return RouteDecision(
                intent="personal_notes",
                confidence=scores.personal_notes,
                reason=f"local:{reason}:personal_notes",
                requires_upload=not has_uploaded_document,
            )
        if scores.institutional >= 0.32 and (
            scores.institutional + 0.08 >= scores.educational
            or (scores.matched_topics and scores.educational > 0)
        ):
            return RouteDecision(
                intent="institutional_faq",
                confidence=max(scores.institutional, 0.45 if scores.matched_topics else scores.institutional),
                reason=(
                    f"local:{reason}:institutional"
                    f":topics={','.join(scores.matched_topics) or 'signals'}"
                ),
                requires_upload=False,
            )
        return self._fallback(reason)

    @staticmethod
    def _fallback(reason: str) -> RouteDecision:
        return RouteDecision(
            intent="out_of_scope",
            confidence=0.0,
            reason=f"fallback:{reason}",
            requires_upload=False,
        )

    def _log_decision(
        self,
        query: str,
        decision: RouteDecision,
        started: float,
        *,
        parse_ok: bool,
        normalized: str,
        scores: IntentScores,
    ) -> None:
        latency_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "IntentRouter decision | query=%r | normalized=%r | intent=%s | "
            "confidence=%.3f | scores={{inst=%.3f notes=%.3f esc=%.3f edu=%.3f}} | "
            "topics=%s | requires_upload=%s | latency_ms=%.2f | model=%s | "
            "parse_ok=%s | reason=%s | route=%s",
            query[:200],
            (normalized or "")[:200],
            decision.intent,
            decision.confidence,
            scores.institutional,
            scores.personal_notes,
            scores.escalate,
            scores.educational,
            list(scores.matched_topics),
            decision.requires_upload,
            latency_ms,
            self._model_name,
            parse_ok,
            decision.reason,
            decision.intent,
        )


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    """Parse a JSON object from model output, tolerating optional fences."""
    text = (raw or "").strip()
    if not text:
        return None

    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


_router: IntentRouter | None = None


def get_intent_router() -> IntentRouter:
    """Return the process-wide IntentRouter singleton."""
    global _router
    if _router is None:
        _router = IntentRouter()
    return _router
