"""
Response formatter for chat orchestration.

Produces markdown-ready assistant content and a consistent metadata envelope.
ChatService must not format user-facing strings itself.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from backend.app.models.chat_models import (
    FormattedAssistantContent,
    RouteDecision,
    SessionContext,
)
from backend.app.services.citation_builder import CitationBuilder, SourceType
from backend.app.services.context_builder import BuiltContext
from backend.app.services.escalation_manager import EscalationDecision
from backend.app.services.llm_service import GenerationResult
from backend.app.services.ticket_service import EscalationTicket
from src.retrieval_types import SearchResponse


def format_timestamp(epoch_seconds: float | None = None) -> str:
    """Return an ISO-8601 UTC timestamp string."""
    if epoch_seconds is None:
        dt = datetime.now(timezone.utc)
    else:
        dt = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


class ResponseFormatter:
    """Formats assistant replies for the product UI."""

    def __init__(self, citation_builder: CitationBuilder | None = None) -> None:
        self._citation_builder = citation_builder or CitationBuilder()

    def format_generated_reply(
        self,
        *,
        decision: RouteDecision,
        search_response: SearchResponse,
        built_context: BuiltContext,
        generation: GenerationResult,
        source_label: str,
        search_latency_ms: float,
        total_latency_ms: float,
        router_model: str,
        knowledge_mode: str = "grounded",
        knowledge_mode_reason: str = "",
        fallback_used: bool = False,
        retrieval_succeeded: bool = True,
    ) -> FormattedAssistantContent:
        """Combine grounded / hybrid LLM markdown with retrieval + citation metadata."""
        results = list(search_response.results)
        top_score = results[0].similarity_score if results else None

        if knowledge_mode == "general_ai":
            mode = "general_ai" if generation.success else "generation_error"
        elif knowledge_mode == "insufficient_institutional_data":
            mode = "insufficient_institutional_data"
        elif generation.success:
            mode = "generated"
        else:
            mode = "generation_error"
        if knowledge_mode == "grounded" and not results:
            mode = "retrieval_empty"

        source_type = _resolve_source_type(source_label, decision.intent)
        # Citations only for grounded retrieval answers.
        citation_hits = results if knowledge_mode == "grounded" else []
        citation_result = self._citation_builder.build(
            citation_hits,
            source_type=source_type,
        )
        citations = citation_result.to_dicts()

        prompt_length = int(built_context.statistics.get("context_characters") or 0)
        if knowledge_mode == "general_ai":
            prompt_length = len((generation.selection or {}).get("question", "") or "") or prompt_length

        knowledge_badge = _knowledge_badge(knowledge_mode, source_type)

        metadata: dict[str, Any] = {
            "intent": decision.intent,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "requires_upload": decision.requires_upload,
            "latency_ms": round(total_latency_ms, 2),
            "search_latency_ms": round(search_latency_ms, 2),
            "generation_latency_ms": round(generation.latency_ms, 2),
            "retrieved_count": len(results),
            "context_chunks": built_context.statistics.get("selected_chunks", 0),
            "context_characters": built_context.statistics.get("context_characters", 0),
            "prompt_length": prompt_length,
            "top_similarity": round(top_score, 4) if top_score is not None else None,
            "source_label": source_label,
            "source_type": source_type,
            "knowledge_mode": knowledge_mode,
            "knowledge_mode_reason": knowledge_mode_reason,
            "fallback_used": fallback_used,
            "retrieval_succeeded": retrieval_succeeded,
            "knowledge_badge": knowledge_badge,
            "safety_decision": "allowed",
            "generation_blocked": False,
            "escalation_category": None,
            "escalation_severity": None,
            "ticket_created": False,
            "ticket_id": None,
            "support_resource": None,
            "provider": generation.provider,
            "model": generation.model,
            "prompt_tokens": generation.prompt_tokens,
            "completion_tokens": generation.completion_tokens,
            "total_tokens": generation.total_tokens,
            "provider_selection": generation.selection,
            "citations": citations,
            "citation_stats": citation_result.statistics,
            "router": "gemini_intent_v1",
            "router_model": router_model,
            "sources": [s.to_dict() for s in built_context.sources]
            if knowledge_mode == "grounded"
            else [],
            "chunks": [hit.to_dict() for hit in results] if knowledge_mode == "grounded" else [],
            "referenced_documents": [c["document"] for c in citations],
            "referenced_chunk_ids": [
                chunk_id
                for citation in citations
                for chunk_id in citation.get("chunk_ids", [])
            ],
        }
        status = "success"
        if not generation.success and knowledge_mode != "insufficient_institutional_data":
            status = "error"
        return FormattedAssistantContent(
            content=generation.content.strip(),
            mode=mode,
            source=source_label if knowledge_mode == "grounded" else (
                "general_ai" if knowledge_mode == "general_ai" else None
            ),
            status=status,
            metadata=metadata,
        )

    def format_greeting_reply(
        self,
        *,
        user_message: str,
        decision: RouteDecision,
        latency_ms: float,
        router_model: str,
    ) -> FormattedAssistantContent:
        """Friendly welcome for hi/hey/hello — not a refuse, not RAG."""
        return self.format_chitchat_reply(
            user_message=user_message,
            decision=decision,
            latency_ms=latency_ms,
            router_model=router_model,
        )

    def format_chitchat_reply(
        self,
        *,
        user_message: str,
        decision: RouteDecision,
        latency_ms: float,
        router_model: str,
    ) -> FormattedAssistantContent:
        """Lightweight conversation — greetings, thanks, capability asks."""
        content = _chitchat_content(user_message)
        metadata: dict[str, Any] = {
            "intent": decision.intent,
            "confidence": decision.confidence,
            "reason": f"{decision.reason}|chitchat",
            "requires_upload": decision.requires_upload,
            "latency_ms": round(latency_ms, 2),
            "retrieved_count": 0,
            "top_similarity": None,
            "knowledge_mode": None,
            "knowledge_mode_reason": "chitchat",
            "fallback_used": False,
            "retrieval_succeeded": False,
            "knowledge_badge": None,
            "safety_decision": "allowed",
            "generation_blocked": False,
            "escalation_category": None,
            "escalation_severity": None,
            "ticket_created": False,
            "ticket_id": None,
            "support_resource": None,
            "citations": [],
            "citation_stats": {
                "citation_count": 0,
                "input_hits": 0,
                "source_types": [],
                "documents": [],
            },
            "router": "gemini_intent_v1",
            "router_model": router_model,
            "chunks": [],
            "sources": [],
            "referenced_documents": [],
            "referenced_chunk_ids": [],
            "is_greeting": True,
            "is_chitchat": True,
        }
        return FormattedAssistantContent(
            content=content,
            mode="greeting",
            source=None,
            status="success",
            metadata=metadata,
        )

    def format_non_retrieval_reply(
        self,
        *,
        user_message: str,
        decision: RouteDecision,
        session_context: SessionContext,
        latency_ms: float,
        router_model: str,
    ) -> FormattedAssistantContent:
        """Placeholders for escalate / out_of_scope / missing upload."""
        content = self._non_retrieval_content(
            intent=decision.intent,
            user_message=user_message,
            session_context=session_context,
            requires_upload=decision.requires_upload,
        )
        metadata: dict[str, Any] = {
            "intent": decision.intent,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "requires_upload": decision.requires_upload,
            "latency_ms": round(latency_ms, 2),
            "retrieved_count": 0,
            "top_similarity": None,
            "knowledge_mode": None,
            "knowledge_mode_reason": None,
            "fallback_used": False,
            "retrieval_succeeded": False,
            "knowledge_badge": None,
            "safety_decision": "allowed",
            "generation_blocked": False,
            "escalation_category": None,
            "escalation_severity": None,
            "ticket_created": False,
            "ticket_id": None,
            "support_resource": None,
            "citations": [],
            "citation_stats": {
                "citation_count": 0,
                "input_hits": 0,
                "source_types": [],
                "documents": [],
            },
            "router": "gemini_intent_v1",
            "router_model": router_model,
            "chunks": [],
            "sources": [],
            "referenced_documents": [],
            "referenced_chunk_ids": [],
        }
        return FormattedAssistantContent(
            content=content,
            mode="placeholder",
            source=None,
            status="success",
            metadata=metadata,
        )

    def format_escalation_reply(
        self,
        *,
        user_message: str,
        decision: RouteDecision,
        escalation: EscalationDecision,
        ticket: EscalationTicket | None,
        latency_ms: float,
        router_model: str,
        knowledge_mode: str | None = None,
        provider: str | None = None,
    ) -> FormattedAssistantContent:
        """Safe support response — no counselling / medical / legal advice."""
        content = _safe_escalation_content(
            user_message=user_message,
            escalation=escalation,
        )
        resource = escalation.contact_resource.to_dict()
        metadata: dict[str, Any] = {
            "intent": decision.intent,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "requires_upload": decision.requires_upload,
            "latency_ms": round(latency_ms, 2),
            "retrieved_count": 0,
            "top_similarity": None,
            "knowledge_mode": knowledge_mode,
            "provider": provider,
            "model": None,
            "safety_decision": "blocked_escalate",
            "generation_blocked": True,
            "escalation_category": escalation.category,
            "escalation_category_label": escalation.category_label,
            "escalation_severity": escalation.severity,
            "ticket_created": ticket is not None,
            "ticket_id": ticket.ticket_id if ticket else None,
            "support_resource": resource,
            "escalation": escalation.to_dict(),
            "citations": [],
            "citation_stats": {
                "citation_count": 0,
                "input_hits": 0,
                "source_types": [],
                "documents": [],
            },
            "router": "gemini_intent_v1",
            "router_model": router_model,
            "chunks": [],
            "sources": [],
            "referenced_documents": [],
            "referenced_chunk_ids": [],
            "knowledge_badge": None,
            "fallback_used": False,
            "retrieval_succeeded": False,
        }
        return FormattedAssistantContent(
            content=content,
            mode="escalation",
            source="safety_layer",
            status="success",
            metadata=metadata,
        )

    def _non_retrieval_content(
        self,
        *,
        intent: str,
        user_message: str,
        session_context: SessionContext,
        requires_upload: bool,
    ) -> str:
        quoted = _short_quote(user_message)

        if intent == "personal_notes" and (requires_upload or not session_context.has_notes):
            return (
                "I'd like to search your uploaded notes, but no document is available "
                "for this session yet.\n\n"
                f"> {quoted}\n\n"
                "Please upload a PDF, DOCX, or TXT file from the **Upload notes** panel, "
                "then ask again."
            )

        if intent == "escalate":
            # Prefer Safety Layer path; this is a last-resort fallback only.
            return (
                "I've identified this as a situation that requires human support.\n\n"
                f"> {quoted}\n\n"
                "I'm not able to handle this here. Please reach out to campus counseling, "
                "student affairs, a trusted person, or emergency services if you are in "
                "immediate danger.\n\n"
                "You are not alone — trained human support is the right next step."
            )

        return (
            "I can help with campus questions, your uploaded notes, study topics, "
            "and light helpful asks (study tips, careers, book/movie ideas).\n\n"
            f"> {quoted}\n\n"
            "Could you rephrase that, or tell me what you'd like help with?"
        )


def _chitchat_content(user_message: str) -> str:
    text = (user_message or "").strip().lower()
    capabilities = (
        "I can help with:\n"
        "- Campus questions (fees, hostel, admissions, exams, library)\n"
        "- Academic explanations (ML, DSA, OS, DBMS, and more)\n"
        "- Questions about notes you upload\n"
        "- Light helpful asks (study tips, careers, book/movie ideas)\n\n"
        "What would you like to know?"
    )
    if re.search(r"\b(thanks?|thank you|thx|ty)\b", text):
        return "You're welcome! Happy to help anytime — ask whenever you're ready."
    if re.search(r"\b(bye|goodbye|see you|cya)\b", text):
        return "Bye! Take care — I'm here whenever you need help with campus or study questions."
    if re.search(r"\bhow are you\b|\bhow'?s it going\b|\bwhat'?s up\b", text):
        return (
            "I'm doing well, thanks for asking! Ready to help whenever you are.\n\n"
            + capabilities
        )
    if re.search(r"\bwho are you\b|\bwhat are you\b", text):
        return (
            "I'm your AI Student Assistant — a campus and study helper for this chatbot.\n\n"
            + capabilities
        )
    if re.search(r"\bwhat (can|do) you do\b", text):
        return "Here's what I'm best at:\n\n" + capabilities
    if re.search(r"\b(ok(ay)?|cool|great|awesome|got it)\b", text) and len(text) < 24:
        return "Sounds good. What would you like to dig into next?"
    return (
        "Hi! I'm your AI Student Assistant.\n\n"
        + capabilities
    )


def _resolve_source_type(source_label: str, intent: str) -> SourceType:
    label = (source_label or "").lower()
    if intent == "personal_notes" or "session" in label or "notes" in label:
        return "uploaded_notes"
    return "institutional"


def _knowledge_badge(knowledge_mode: str, source_type: SourceType) -> dict[str, str] | None:
    """Compact badge payload for the frontend (label + tone)."""
    if knowledge_mode == "grounded":
        if source_type == "uploaded_notes":
            return {
                "kind": "uploaded_notes",
                "label": "Uploaded Notes",
                "emoji": "📄",
            }
        return {
            "kind": "knowledge_base",
            "label": "Knowledge Base",
            "emoji": "📚",
        }
    if knowledge_mode == "general_ai":
        return {
            "kind": "general_ai",
            "label": "General AI Knowledge",
            "emoji": "✨",
            "disclaimer": (
                "This answer is based on the AI model's general knowledge and was "
                "not found in the institutional knowledge base."
            ),
        }
    return None


def _safe_escalation_content(
    *,
    user_message: str,
    escalation: EscalationDecision,
) -> str:
    """Acknowledge concern and point to institutional resources — no advice."""
    quoted = _short_quote(user_message)
    resource = escalation.contact_resource
    label = escalation.category_label or escalation.category
    lines = [
        "Thank you for sharing this. Your safety and wellbeing matter.",
        "",
        f"> {quoted}",
        "",
        f"This looks like a **{label}** situation that needs trained human support "
        f"(severity: **{escalation.severity}**).",
        "",
        "I can't provide counselling, medical, or legal advice here. "
        "Please contact the appropriate campus office:",
        "",
        f"- **{resource.name}**",
        f"- Office: {resource.office}",
        f"- Email: {resource.email}",
        f"- Phone: {resource.phone}",
        f"- Hours: {resource.office_hours}",
    ]
    if resource.emergency_notice:
        lines.extend(["", f"**Important:** {resource.emergency_notice}"])
    lines.extend(
        [
            "",
            "If you are in immediate danger, contact campus security or local "
            "emergency services right away. You are not alone.",
        ]
    )
    return "\n".join(lines)


def _short_quote(text: str, limit: int = 160) -> str:
    cleaned = (text or "").strip().replace("\n", " ")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."
