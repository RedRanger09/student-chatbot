"""
ChatService — central orchestration layer for POST /chat.

Request flow:
    User Message
        → IntentRouter.classify
        → Safety Layer (deterministic guardrails)
            → blocked → EscalationManager → TicketService → safe response
            → allowed → continue
        → Institutional KB / Session KB search
        → ContextBuilder
        → KnowledgeModeClassifier (post-retrieval)
        → LLMService → ProviderFactory → Gemini | LM Studio
        → ResponseFormatter
        → Conversation Store

ChatService never imports Gemini or LM Studio directly.
Unsafe / escalation requests never reach the LLM.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Iterator, Sequence
from typing import Any

from backend.app.models.chat_models import (
    ChatTurnRequest,
    ChatTurnResult,
    RouteDecision,
    SessionContext,
)
from backend.app.services.context_builder import ContextBuilder
from backend.app.services.context_resolution import (
    ResolvedContext,
    resolve_followup_context,
    select_history_for_prompt,
)
from backend.app.services.conversation_memory import (
    get_max_history_messages,
    history_as_dicts,
    load_recent_history,
)
from backend.app.services.followup_suggestions import suggest_followups
from backend.app.services.intent_router import IntentRouter, get_intent_router
from backend.app.services.knowledge_mode_classifier import (
    KnowledgeModeClassifier,
    KnowledgeModeDecision,
)
from backend.app.services.llm_service import GenerationResult, LLMService, get_llm_service
from backend.app.services.response_formatter import ResponseFormatter, format_timestamp
from backend.app.services.escalation_manager import EscalationDecision
from backend.app.services.safety_layer import SafetyLayer, get_safety_layer
from backend.app.services.ticket_service import TicketService, get_ticket_service
from src.conversations.store import ConversationStore, Message, get_conversation_store
from src.retrieval_types import SearchResponse
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ChatServiceError(Exception):
    """Base error for chat orchestration."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class EmptyMessageError(ChatServiceError):
    def __init__(self) -> None:
        super().__init__("Message must not be empty", status_code=400)


class ConversationNotFoundError(ChatServiceError):
    def __init__(self, conversation_id: str) -> None:
        super().__init__(
            f"Conversation not found: {conversation_id}",
            status_code=404,
        )


class ChatService:
    """Sole owner of chat request processing."""

    def __init__(
        self,
        store: ConversationStore | None = None,
        formatter: ResponseFormatter | None = None,
        intent_router: IntentRouter | None = None,
        session_context_provider: Any | None = None,
        kb_service: Any | None = None,
        context_builder: ContextBuilder | None = None,
        llm_service: LLMService | None = None,
        knowledge_mode_classifier: KnowledgeModeClassifier | None = None,
        safety_layer: SafetyLayer | None = None,
        ticket_service: TicketService | None = None,
    ) -> None:
        self._store = store or get_conversation_store()
        self._formatter = formatter or ResponseFormatter()
        self._intent_router = intent_router or get_intent_router()
        self._session_context_provider = session_context_provider
        self._kb_service = kb_service
        self._context_builder = context_builder or ContextBuilder()
        self._llm_service = llm_service or get_llm_service()
        self._knowledge_mode_classifier = (
            knowledge_mode_classifier or KnowledgeModeClassifier()
        )
        self._safety_layer = safety_layer or get_safety_layer()
        self._ticket_service = ticket_service or get_ticket_service()

    def process_message(self, request: ChatTurnRequest) -> ChatTurnResult:
        """Route → retrieve → build context → generate grounded answer."""
        started = time.perf_counter()
        text = (request.message or "").strip()
        if not text:
            raise EmptyMessageError()

        logger.info(
            "ChatService incoming request | conversation_id=%s | session_id=%s | chars=%s",
            request.conversation_id,
            request.session_id,
            len(text),
        )

        try:
            conversation_id = self._ensure_conversation(
                request.conversation_id,
                owner_id=request.client_id or "",
            )
            user_message = self.create_message(conversation_id, "user", text)
            history = self._load_history(conversation_id, exclude={user_message.id})
            resolved = resolve_followup_context(text, history)
            prompt_history = select_history_for_prompt(history, resolved=resolved)
            route_text = resolved.expanded_query or text

            logger.info(
                "ChatService memory | conversation_id=%s | memory_size=%s | "
                "injected=%s | followup=%s | topic=%r | expanded=%r",
                conversation_id,
                len(history),
                len(prompt_history),
                resolved.is_followup,
                resolved.resolved_topic,
                (resolved.expanded_query or "")[:160],
            )

            session_context = self._resolve_session_context(request.session_id)
            decision = self._intent_router.classify(
                route_text,
                has_uploaded_document=session_context.has_notes,
            )
            decision = self._prefer_followup_domain(
                decision,
                resolved=resolved,
                session_context=session_context,
            )
            logger.info(
                "ChatService detected intent=%s confidence=%.3f requires_upload=%s "
                "route_text=%r",
                decision.intent,
                decision.confidence,
                decision.requires_upload,
                route_text[:160],
            )

            # Safety Layer runs before any retrieval / generation.
            safety = self._safety_layer.check(text, intent=decision.intent)
            if not safety.allowed and safety.escalation is not None:
                formatted = self._handle_escalation(
                    text=text,
                    decision=decision,
                    conversation_id=conversation_id,
                    escalation=safety.escalation,
                    started=started,
                )
            else:
                formatted = self._dispatch(
                    text=text,
                    decision=decision,
                    session_context=session_context,
                    session_id=request.session_id,
                    started=started,
                    history=prompt_history,
                    retrieval_query=route_text,
                )

            formatted = self._attach_conversational_meta(
                formatted,
                question=text,
                history=prompt_history,
                streaming_enabled=False,
                streaming_duration_ms=None,
                resolved=resolved,
            )

            # Persist formatter metadata (including citations) on the message
            # so Sources / AI Inspector work after conversation reload.
            assistant_message = self.create_message(
                conversation_id,
                "assistant",
                formatted.content,
                meta={
                    "mode": formatted.mode,
                    "status": formatted.status,
                    "message_anchor": True,
                    **formatted.metadata,
                },
            )

            result = self.build_response(
                conversation_id=conversation_id,
                user_message=user_message,
                assistant_message=assistant_message,
                formatted_content=formatted.content,
                status=formatted.status,
                mode=formatted.mode,
                source=formatted.source,
                metadata=formatted.metadata,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )

            logger.info(
                "ChatService complete | conversation_id=%s | intent=%s | mode=%s | "
                "provider=%s | retrieved=%s | latency_ms=%.2f",
                conversation_id,
                decision.intent,
                result.mode,
                result.metadata.get("provider"),
                result.metadata.get("retrieved_count"),
                result.latency_ms,
            )
            return result
        except ChatServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("ChatService unexpected failure: %s", exc)
            raise ChatServiceError(
                "Unexpected failure while processing chat message",
                status_code=500,
            ) from exc

    def process_message_stream(
        self, request: ChatTurnRequest
    ) -> Iterator[dict[str, Any]]:
        """
        Same orchestration as ``process_message``, with token streaming.

        Yields SSE-ready event dicts:
          - start: conversation + user message + provisional assistant id
          - token: text delta
          - done: final ChatTurnResult-compatible payload
          - error: failure detail
        """
        started = time.perf_counter()
        text = (request.message or "").strip()
        if not text:
            raise EmptyMessageError()

        try:
            conversation_id = self._ensure_conversation(
                request.conversation_id,
                owner_id=request.client_id or "",
            )
            user_message = self.create_message(conversation_id, "user", text)
            history = self._load_history(conversation_id, exclude={user_message.id})
            resolved = resolve_followup_context(text, history)
            prompt_history = select_history_for_prompt(history, resolved=resolved)
            route_text = resolved.expanded_query or text
            provisional_id = f"stream-{uuid.uuid4()}"

            logger.info(
                "ChatService memory(stream) | conversation_id=%s | memory_size=%s | "
                "injected=%s | followup=%s | topic=%r | expanded=%r",
                conversation_id,
                len(history),
                len(prompt_history),
                resolved.is_followup,
                resolved.resolved_topic,
                (resolved.expanded_query or "")[:160],
            )

            yield {
                "event": "start",
                "conversation_id": conversation_id,
                "user_message": user_message.to_dict(),
                "assistant_message_id": provisional_id,
                "streaming": True,
                "history_messages_used": len(prompt_history),
                "conversation_context_length": get_max_history_messages(),
            }

            session_context = self._resolve_session_context(request.session_id)
            decision = self._intent_router.classify(
                route_text,
                has_uploaded_document=session_context.has_notes,
            )
            decision = self._prefer_followup_domain(
                decision,
                resolved=resolved,
                session_context=session_context,
            )
            safety = self._safety_layer.check(text, intent=decision.intent)

            stream_started = time.perf_counter()
            if not safety.allowed and safety.escalation is not None:
                formatted = self._handle_escalation(
                    text=text,
                    decision=decision,
                    conversation_id=conversation_id,
                    escalation=safety.escalation,
                    started=started,
                )
                for piece in _chunk_text(formatted.content, size=48):
                    yield {"event": "token", "delta": piece}
            else:
                formatted = None
                for item in self._dispatch_stream(
                    text=text,
                    decision=decision,
                    session_context=session_context,
                    session_id=request.session_id,
                    started=started,
                    history=prompt_history,
                    retrieval_query=route_text,
                ):
                    if isinstance(item, str):
                        yield {"event": "token", "delta": item}
                    else:
                        formatted = item

                if formatted is None:
                    raise ChatServiceError(
                        "Streaming generation produced no formatted reply",
                        status_code=500,
                    )

            streaming_duration_ms = (time.perf_counter() - stream_started) * 1000.0
            formatted = self._attach_conversational_meta(
                formatted,
                question=text,
                history=prompt_history,
                streaming_enabled=True,
                streaming_duration_ms=streaming_duration_ms,
                resolved=resolved,
            )

            assistant_message = self.create_message(
                conversation_id,
                "assistant",
                formatted.content,
                meta={
                    "mode": formatted.mode,
                    "status": formatted.status,
                    "message_anchor": True,
                    **formatted.metadata,
                },
            )
            result = self.build_response(
                conversation_id=conversation_id,
                user_message=user_message,
                assistant_message=assistant_message,
                formatted_content=formatted.content,
                status=formatted.status,
                mode=formatted.mode,
                source=formatted.source,
                metadata=formatted.metadata,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
            yield {
                "event": "done",
                "conversation_id": result.conversation_id,
                "message_id": result.message_id,
                "role": result.role,
                "content": result.content,
                "status": result.status,
                "mode": result.mode,
                "source": result.source,
                "streaming_supported": True,
                "timestamp": result.timestamp,
                "metadata": result.metadata,
                "user_message": result.user_message,
                "assistant_message": result.assistant_message,
                "latency_ms": result.latency_ms,
            }
        except ChatServiceError as exc:
            yield {"event": "error", "detail": exc.message, "status_code": exc.status_code}
        except Exception as exc:  # noqa: BLE001
            logger.exception("ChatService stream failure: %s", exc)
            yield {
                "event": "error",
                "detail": "Unexpected failure while streaming chat message",
                "status_code": 500,
            }

    def create_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        meta: dict[str, Any] | None = None,
    ) -> Message:
        message = self._store.add_message(
            conversation_id,
            role=role,  # type: ignore[arg-type]
            content=content,
            meta=meta,
        )
        if message is None:
            raise ConversationNotFoundError(conversation_id)
        return message

    def build_response(
        self,
        *,
        conversation_id: str,
        user_message: Message,
        assistant_message: Message,
        formatted_content: str,
        status: str,
        mode: str,
        source: str | None,
        metadata: dict[str, Any],
        latency_ms: float,
    ) -> ChatTurnResult:
        meta = dict(metadata)
        meta["latency_ms"] = round(latency_ms, 2)
        return ChatTurnResult(
            conversation_id=conversation_id,
            message_id=assistant_message.id,
            role="assistant",
            content=formatted_content,
            status=status,
            mode=mode,
            source=source,
            streaming_supported=True,
            timestamp=format_timestamp(assistant_message.created_at),
            metadata=meta,
            user_message=user_message.to_dict(),
            assistant_message=assistant_message.to_dict(),
            latency_ms=round(latency_ms, 2),
        )

    def store_conversation(self, title: str = "New chat", *, owner_id: str = "") -> str:
        conversation = self._store.create(title=title, owner_id=owner_id)
        return conversation.id

    # ------------------------------------------------------------------
    # Safety / Escalation
    # ------------------------------------------------------------------

    def _handle_escalation(
        self,
        *,
        text: str,
        decision: RouteDecision,
        conversation_id: str,
        escalation: EscalationDecision,
        started: float,
    ):
        """Create ticket (if required) and return a safe support response."""
        ticket = None
        if escalation.requires_ticket:
            ticket = self._ticket_service.create_ticket(
                conversation_id=conversation_id,
                category=escalation.category,
                severity=escalation.severity,
                message=text,
                knowledge_mode=None,
                provider=None,
            )
            logger.info(
                "ChatService escalation ticket | ticket_id=%s | category=%s | "
                "severity=%s | generation_blocked=true",
                ticket.ticket_id,
                escalation.category,
                escalation.severity,
            )
        else:
            logger.info(
                "ChatService escalation without ticket | category=%s | severity=%s | "
                "generation_blocked=true",
                escalation.category,
                escalation.severity,
            )

        return self._formatter.format_escalation_reply(
            user_message=text,
            decision=decision,
            escalation=escalation,
            ticket=ticket,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            router_model=self._intent_router.model_name,
            knowledge_mode=None,
            provider=None,
        )

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(
        self,
        *,
        text: str,
        decision: RouteDecision,
        session_context: SessionContext,
        session_id: str | None,
        started: float,
        history: Sequence[dict[str, str]] | None = None,
        retrieval_query: str | None = None,
    ):
        router_model = self._intent_router.model_name
        search_text = (retrieval_query or text).strip() or text

        if decision.intent == "institutional_faq":
            from backend.app.services.knowledge_mode_classifier import (
                is_external_institution_query,
                is_lightweight_general_query,
                is_operational_institutional_query,
            )
            from backend.app.services.intent_signals import search_query_for_retrieval

            # Never answer another institution using this campus's KB.
            if is_external_institution_query(text) or is_external_institution_query(
                search_text
            ):
                return self._external_institution_reply(
                    text=text,
                    decision=decision,
                    started=started,
                    router_model=router_model,
                )
            # Avoid library "book" keyword capturing movie/book recommendations.
            if is_lightweight_general_query(text) and not is_operational_institutional_query(
                search_text
            ):
                return self._maybe_general_educational(
                    text=text,
                    decision=decision,
                    session_context=session_context,
                    started=started,
                    router_model=router_model,
                    history=history,
                )
            search_q = search_query_for_retrieval(search_text)
            return self._retrieve_and_generate(
                text=text,
                decision=decision,
                source_label="institutional",
                search_fn=lambda: self._get_kb_service().search_institutional(search_q),
                started=started,
                router_model=router_model,
                history=history,
            )

        if decision.intent == "personal_notes":
            if decision.requires_upload or not session_context.has_notes or not session_id:
                return self._formatter.format_non_retrieval_reply(
                    user_message=text,
                    decision=decision,
                    session_context=session_context,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    router_model=router_model,
                )
            return self._retrieve_and_generate(
                text=text,
                decision=decision,
                source_label="session notes",
                search_fn=lambda: self._search_session(session_id, search_text),
                started=started,
                router_model=router_model,
                history=history,
            )

        # escalate is handled by Safety Layer before dispatch.
        # out_of_scope: try institutional retrieval when campus signals exist,
        # then fall back to General AI / refuse.
        if decision.intent == "out_of_scope":
            rescued = self._try_institutional_rescue(
                text=text,
                decision=decision,
                started=started,
                router_model=router_model,
                history=history,
                retrieval_query=search_text,
            )
            if rescued is not None:
                return rescued
            return self._maybe_general_educational(
                text=text,
                decision=decision,
                session_context=session_context,
                started=started,
                router_model=router_model,
                history=history,
            )

        return self._formatter.format_non_retrieval_reply(
            user_message=text,
            decision=decision,
            session_context=session_context,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            router_model=router_model,
        )

    def _prefer_followup_domain(
        self,
        decision: RouteDecision,
        *,
        resolved: ResolvedContext,
        session_context: SessionContext,
    ) -> RouteDecision:
        """
        Keep elliptical follow-ups in the prior domain when routing would
        otherwise bounce them to out_of_scope / wrong KB.
        """
        if not resolved.is_followup or resolved.topic_switched:
            return decision
        domain = resolved.prior_domain
        if not domain:
            return decision

        # Already on a grounded path — leave alone.
        if decision.intent in ("institutional_faq", "personal_notes", "escalate"):
            return decision

        if domain == "notes" and session_context.has_notes:
            logger.info(
                "ChatService followup domain stick | notes | topic=%r | was=%s",
                resolved.resolved_topic,
                decision.intent,
            )
            return RouteDecision(
                intent="personal_notes",
                confidence=max(float(decision.confidence or 0.0), 0.7),
                reason=f"{decision.reason}|followup:notes_context",
                requires_upload=False,
            )

        if domain == "institutional":
            logger.info(
                "ChatService followup domain stick | institutional | topic=%r | was=%s",
                resolved.resolved_topic,
                decision.intent,
            )
            return RouteDecision(
                intent="institutional_faq",
                confidence=max(float(decision.confidence or 0.0), 0.7),
                reason=f"{decision.reason}|followup:institutional_context",
                requires_upload=False,
            )

        # Educational follow-ups stay on General AI (out_of_scope → educational).
        if domain == "educational" and decision.intent == "out_of_scope":
            return RouteDecision(
                intent="out_of_scope",
                confidence=decision.confidence,
                reason=f"{decision.reason}|followup:educational_context",
                requires_upload=False,
            )

        return decision

    def _try_institutional_rescue(
        self,
        *,
        text: str,
        decision: RouteDecision,
        started: float,
        router_model: str,
        history: Sequence[dict[str, str]] | None = None,
        retrieval_query: str | None = None,
    ):
        """
        Retrieval-before-fallback for uncertain out_of_scope campus asks.

        Attempts institutional search using a normalized query. If usable
        chunks exist, answer via Institutional RAG; otherwise return None
        so the caller can continue to General AI / refuse.
        """
        from backend.app.services.intent_signals import (
            search_query_for_retrieval,
            should_try_institutional_retrieval,
        )
        from backend.app.services.knowledge_mode_classifier import (
            is_external_institution_query,
        )

        probe = (retrieval_query or text).strip() or text
        if is_external_institution_query(text) or is_external_institution_query(probe):
            return None
        if not should_try_institutional_retrieval(probe):
            return None

        search_q = search_query_for_retrieval(probe)
        logger.info(
            "ChatService institutional rescue | original=%r | search=%r",
            text[:160],
            search_q[:160],
        )
        try:
            search_response = self._get_kb_service().search_institutional(search_q)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ChatService institutional rescue search failed: %s", exc)
            return None

        built = self._context_builder.build(search_response.results)
        if not search_response.results or built.is_empty:
            logger.info(
                "ChatService institutional rescue miss | falling back | message=%s",
                search_response.message,
            )
            return None

        forced = RouteDecision(
            intent="institutional_faq",
            confidence=max(float(decision.confidence or 0.0), 0.55),
            reason=f"{decision.reason}|rescue:retrieval_before_fallback",
            requires_upload=False,
        )
        logger.info(
            "ChatService institutional rescue hit | chunks=%s | top=%.4f",
            len(search_response.results),
            search_response.results[0].similarity_score,
        )
        return self._retrieve_and_generate(
            text=text,
            decision=forced,
            source_label="institutional",
            search_fn=lambda: search_response,
            started=started,
            router_model=router_model,
            history=history,
        )

    def _maybe_general_educational(
        self,
        *,
        text: str,
        decision: RouteDecision,
        session_context: SessionContext,
        started: float,
        router_model: str,
        history: Sequence[dict[str, str]] | None = None,
    ):
        """
        First-class General AI path for educational out-of-scope questions.

        This is independent of RAG. Campus operational questions never arrive
        here (they are routed to institutional_faq first).
        """
        from backend.app.services.knowledge_mode_classifier import (
            is_chitchat_query,
            is_educational_query,
            is_external_institution_query,
            is_lightweight_general_query,
            is_operational_institutional_query,
        )

        # Chit-chat (hi, thanks, how are you) — never academic refuse.
        if is_chitchat_query(text):
            logger.info("ChatService chitchat path | query=%r", text[:80])
            return self._formatter.format_chitchat_reply(
                user_message=text,
                decision=decision,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                router_model=router_model,
            )

        # Another institution asked via out_of_scope — do not invent local policy.
        if is_external_institution_query(text):
            return self._external_institution_reply(
                text=text,
                decision=decision,
                started=started,
                router_model=router_model,
            )

        # Campus operational facts without RAG must not invent via General AI.
        if is_operational_institutional_query(text):
            knowledge = KnowledgeModeDecision(
                mode="insufficient_institutional_data",
                reason="institution_specific_out_of_scope_no_retrieval",
                retrieval_succeeded=False,
                fallback_used=False,
            )
            generation = self._insufficient_institutional_reply(
                text=text,
                source_label="institutional",
                search_response=SearchResponse(
                    results=[],
                    message="No relevant content found in the institutional knowledge base.",
                ),
                knowledge=knowledge,
            )
            empty = SearchResponse(results=[], message=None)
            built = self._context_builder.build([])
            return self._formatter.format_generated_reply(
                decision=decision,
                search_response=empty,
                built_context=built,
                generation=generation,
                source_label="institutional",
                search_latency_ms=0.0,
                total_latency_ms=(time.perf_counter() - started) * 1000.0,
                router_model=router_model,
                knowledge_mode="insufficient_institutional_data",
                knowledge_mode_reason=knowledge.reason,
                fallback_used=False,
                retrieval_succeeded=False,
            )

        allow_general = (
            is_educational_query(text) or is_lightweight_general_query(text)
        ) and not is_operational_institutional_query(text)

        if allow_general:
            knowledge = self._knowledge_mode_classifier.decide(
                text,
                has_usable_chunks=False,
            )
            if knowledge.mode != "general_ai":
                knowledge = KnowledgeModeDecision(
                    mode="general_ai",
                    reason=(
                        "lightweight_general_first_class"
                        if is_lightweight_general_query(text)
                        else "educational_out_of_scope_first_class"
                    ),
                    retrieval_succeeded=False,
                    fallback_used=True,
                )

            logger.info(
                "ChatService General AI path | reason=%s | query=%r",
                knowledge.reason,
                text[:200],
            )
            generation = self._llm_service.generate_general(
                question=text,
                history=history,
            )
            empty = SearchResponse(results=[], message=None)
            built = self._context_builder.build([])
            return self._formatter.format_generated_reply(
                decision=decision,
                search_response=empty,
                built_context=built,
                generation=generation,
                source_label="general_ai",
                search_latency_ms=0.0,
                total_latency_ms=(time.perf_counter() - started) * 1000.0,
                router_model=router_model,
                knowledge_mode="general_ai",
                knowledge_mode_reason=knowledge.reason,
                fallback_used=True,
                retrieval_succeeded=False,
            )

        return self._formatter.format_non_retrieval_reply(
            user_message=text,
            decision=decision,
            session_context=session_context,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            router_model=router_model,
        )

    def _retrieve_and_generate(
        self,
        *,
        text: str,
        decision: RouteDecision,
        source_label: str,
        search_fn: Any,
        started: float,
        router_model: str,
        history: Sequence[dict[str, str]] | None = None,
    ):
        search_started = time.perf_counter()
        search_response: SearchResponse = search_fn()
        search_latency_ms = (time.perf_counter() - search_started) * 1000.0
        self._log_search(
            intent=decision.intent,
            search_response=search_response,
            search_latency_ms=search_latency_ms,
        )

        # RAG-first: always build context from retrieval before any fallback.
        built = self._context_builder.build(search_response.results)
        has_usable = bool(search_response.results) and not built.is_empty
        knowledge = self._knowledge_mode_classifier.decide(
            text,
            has_usable_chunks=has_usable,
        )

        # Uploaded notes must never invent via General AI when retrieval is empty.
        label = (source_label or "").lower()
        if (
            not has_usable
            and knowledge.mode == "general_ai"
            and ("session" in label or "notes" in label)
        ):
            knowledge = KnowledgeModeDecision(
                mode="insufficient_institutional_data",
                reason="personal_notes_without_retrieval",
                retrieval_succeeded=False,
                fallback_used=False,
            )

        # Campus operational facts must never invent via General AI.
        from backend.app.services.knowledge_mode_classifier import (
            is_operational_institutional_query,
        )

        if (
            not has_usable
            and knowledge.mode == "general_ai"
            and "institutional" in label
            and is_operational_institutional_query(text)
        ):
            knowledge = KnowledgeModeDecision(
                mode="insufficient_institutional_data",
                reason="institution_specific_no_retrieval",
                retrieval_succeeded=False,
                fallback_used=False,
            )

        if knowledge.mode == "grounded":
            generation = self._llm_service.generate(
                context=built,
                question=text,
                history=history,
            )
        elif knowledge.mode == "general_ai":
            logger.info(
                "ChatService hybrid fallback → general_ai | reason=%s | query=%r",
                knowledge.reason,
                text[:200],
            )
            generation = self._llm_service.generate_general(
                question=text,
                history=history,
            )
        else:
            generation = self._insufficient_institutional_reply(
                text=text,
                source_label=source_label,
                search_response=search_response,
                knowledge=knowledge,
            )

        return self._formatter.format_generated_reply(
            decision=decision,
            search_response=search_response,
            built_context=built,
            generation=generation,
            source_label=source_label,
            search_latency_ms=search_latency_ms,
            total_latency_ms=(time.perf_counter() - started) * 1000.0,
            router_model=router_model,
            knowledge_mode=knowledge.mode,
            knowledge_mode_reason=knowledge.reason,
            fallback_used=knowledge.fallback_used,
            retrieval_succeeded=knowledge.retrieval_succeeded,
        )

    @staticmethod
    def _insufficient_institutional_reply(
        *,
        text: str,
        source_label: str,
        search_response: SearchResponse,
        knowledge: KnowledgeModeDecision,
    ) -> GenerationResult:
        """Friendly no-guess response for empty retrieval (campus or notes)."""
        quoted = _short_quote(text)
        label = (source_label or "").lower()
        notes_path = (
            "session" in label
            or "notes" in label
            or knowledge.reason == "personal_notes_without_retrieval"
        )

        if notes_path:
            generation_content = (
                "I couldn't find relevant content in your **uploaded notes** for:\n\n"
                f"> {quoted}\n\n"
                f"{search_response.message or 'No matching passages passed the similarity threshold.'}\n\n"
                "Try:\n"
                "- Re-uploading the document\n"
                "- Asking with a chapter title, section heading, or page range\n"
                "- Checking that the file finished indexing\n\n"
                "I won't invent content from your notes when retrieval is empty."
            )
        elif knowledge.reason == "external_institution_no_local_kb":
            generation_content = (
                "That question is about **another institution**, and this chatbot's "
                "local knowledge base only covers **this campus**.\n\n"
                f"> {quoted}\n\n"
                "I won't answer using documents from a different college. "
                "Please check that institution's official website, or ask about "
                "this campus's policies instead."
            )
        else:
            generation_content = (
                "I couldn't find this information in the **institutional knowledge base**.\n\n"
                f"> {quoted}\n\n"
                f"{search_response.message or 'No relevant content passed the similarity threshold.'}\n\n"
                "I won't invent campus policies, fees, or procedures. You can try:\n"
                "- Checking the student ERP / portal\n"
                "- Contacting the administration or the relevant office\n"
                "- Admissions / hostel office for fee-related questions\n"
                "- Rephrasing with more specific campus terms"
            )
        return GenerationResult(
            content=generation_content,
            provider=None,
            model=None,
            latency_ms=0.0,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            selection={
                "mode": "skipped",
                "reason": knowledge.reason,
                "knowledge_mode": knowledge.mode,
                "fallback": False,
            },
            success=True,
        )

    def _external_institution_reply(
        self,
        *,
        text: str,
        decision: RouteDecision,
        started: float,
        router_model: str,
    ):
        """Refuse to mix another institution with this campus's KB."""
        knowledge = KnowledgeModeDecision(
            mode="insufficient_institutional_data",
            reason="external_institution_no_local_kb",
            retrieval_succeeded=False,
            fallback_used=False,
        )
        generation = self._insufficient_institutional_reply(
            text=text,
            source_label="institutional",
            search_response=SearchResponse(results=[], message=None),
            knowledge=knowledge,
        )
        empty = SearchResponse(results=[], message=None)
        built = self._context_builder.build([])
        logger.info(
            "ChatService external institution blocked | query=%r",
            text[:200],
        )
        return self._formatter.format_generated_reply(
            decision=decision,
            search_response=empty,
            built_context=built,
            generation=generation,
            source_label="institutional",
            search_latency_ms=0.0,
            total_latency_ms=(time.perf_counter() - started) * 1000.0,
            router_model=router_model,
            knowledge_mode="insufficient_institutional_data",
            knowledge_mode_reason=knowledge.reason,
            fallback_used=False,
            retrieval_succeeded=False,
        )

    def _search_session(self, session_id: str, text: str) -> SearchResponse:
        kb = self._get_kb_service()
        queries = _session_query_variants(text)
        try:
            best: SearchResponse | None = None
            seen_ids: set[str] = set()
            merged: list = []
            for query in queries:
                response = kb.search_session(session_id, query)
                if best is None:
                    best = response
                for hit in response.results:
                    key = hit.chunk_id or hit.text[:80]
                    if key in seen_ids:
                        continue
                    # Prefer substantive body text over tiny TOC/metadata lines.
                    if _looks_like_metadata_only(hit.text):
                        continue
                    seen_ids.add(key)
                    merged.append(hit)
            if merged:
                merged.sort(key=lambda h: h.similarity_score, reverse=True)
                return SearchResponse(results=merged[: max(5, len(queries) + 2)], message=None)
            if best is not None:
                # Fall back to original results even if metadata-like.
                return best
            return SearchResponse(
                results=[],
                message="No relevant content found in your uploaded document.",
            )
        except KeyError:
            logger.warning("Session search: missing/expired session_id=%s", session_id)
            return SearchResponse(
                results=[],
                message="Your session expired or was not found. Please upload your notes again.",
            )
        except RuntimeError as exc:
            logger.warning("Session search unavailable: %s", exc)
            return SearchResponse(
                results=[],
                message="No uploaded document for this session. Please upload a file first.",
            )

    @staticmethod
    def _log_search(
        *,
        intent: str,
        search_response: SearchResponse,
        search_latency_ms: float,
    ) -> None:
        count = len(search_response.results)
        top = search_response.results[0].similarity_score if count else None
        if count == 0:
            logger.info(
                "ChatService retrieval | intent=%s | no results | "
                "search_latency_ms=%.2f | message=%s",
                intent,
                search_latency_ms,
                search_response.message,
            )
        else:
            logger.info(
                "ChatService retrieval | intent=%s | chunks=%s | "
                "top_similarity=%.4f | search_latency_ms=%.2f",
                intent,
                count,
                top if top is not None else -1.0,
                search_latency_ms,
            )

    def _get_kb_service(self) -> Any:
        if self._kb_service is not None:
            return self._kb_service
        from backend.app.services.kb_service import get_kb_service

        self._kb_service = get_kb_service()
        return self._kb_service

    def _ensure_conversation(
        self,
        conversation_id: str | None,
        *,
        owner_id: str = "",
    ) -> str:
        owner = (owner_id or "").strip()
        if conversation_id:
            existing = self._store.get(conversation_id)
            if existing is None:
                raise ConversationNotFoundError(conversation_id)
            # Reject cross-device access to someone else's chat.
            if owner and not self._store.is_owner(existing, owner):
                raise ConversationNotFoundError(conversation_id)
            # Legacy chats with no owner: claim for this client on first touch.
            if owner and not existing.owner_id:
                existing.owner_id = owner
            return conversation_id
        return self.store_conversation(owner_id=owner)

    def _resolve_session_context(self, session_id: str | None) -> SessionContext:
        if not session_id:
            return SessionContext()
        if self._session_context_provider is not None:
            return self._session_context_provider(session_id)
        from backend.app.services.kb_service import get_kb_service

        kb = get_kb_service().session_manager.get_knowledge_base(session_id)
        if kb is None or not kb.has_index():
            return SessionContext()
        return SessionContext(has_notes=True, document_name=kb.document_name)

    def _load_history(
        self,
        conversation_id: str,
        *,
        exclude: set[str] | None = None,
    ) -> list[dict[str, str]]:
        turns = load_recent_history(
            self._store,
            conversation_id,
            exclude_message_ids=exclude,
        )
        return history_as_dicts(turns)

    def _attach_conversational_meta(
        self,
        formatted: Any,
        *,
        question: str,
        history: Sequence[dict[str, str]],
        streaming_enabled: bool,
        streaming_duration_ms: float | None,
        resolved: ResolvedContext | None = None,
    ) -> Any:
        """Attach follow-ups + memory/streaming inspector fields without redesign."""
        meta = dict(formatted.metadata or {})
        prior_bits = [
            turn.get("content", "")
            for turn in history
            if turn.get("role") == "user"
        ][-2:]
        follow_ups = suggest_followups(
            question=question,
            intent=meta.get("intent"),
            knowledge_mode=meta.get("knowledge_mode"),
            prior_context=" ".join(prior_bits),
        )
        meta["follow_ups"] = follow_ups
        meta["suggested_followups"] = follow_ups  # alias for clients
        meta["history_messages_used"] = len(history)
        meta["conversation_context_length"] = get_max_history_messages()
        meta["streaming_enabled"] = bool(streaming_enabled)
        meta["streaming_duration_ms"] = (
            round(streaming_duration_ms, 2) if streaming_duration_ms is not None else None
        )
        meta["message_anchor"] = True
        if resolved is not None:
            meta["memory_size"] = resolved.history_turns_used
            meta["is_followup"] = resolved.is_followup
            meta["resolved_topic"] = resolved.resolved_topic
            meta["expanded_query"] = resolved.expanded_query
            meta["topic_switched"] = resolved.topic_switched
            meta["prior_domain"] = resolved.prior_domain
            meta["context_resolution_reason"] = resolved.reason
            logger.info(
                "ChatService injected history | memory_size=%s | injected=%s | "
                "followup=%s | topic=%r | resolved_refs=%s | expanded=%r",
                resolved.history_turns_used,
                len(history),
                resolved.is_followup,
                resolved.resolved_topic,
                bool(resolved.is_followup and resolved.resolved_topic),
                (resolved.expanded_query or "")[:160],
            )
        formatted.metadata = meta
        return formatted

    def _dispatch_stream(
        self,
        *,
        text: str,
        decision: RouteDecision,
        session_context: SessionContext,
        session_id: str | None,
        started: float,
        history: Sequence[dict[str, str]] | None = None,
        retrieval_query: str | None = None,
    ) -> Iterator[str | Any]:
        """
        Stream token deltas for generation paths; yield formatted reply last.

        Non-generation paths yield the formatted content as small chunks then
        the FormattedAssistantContent object.
        """
        router_model = self._intent_router.model_name
        search_text = (retrieval_query or text).strip() or text

        if decision.intent == "institutional_faq":
            from backend.app.services.knowledge_mode_classifier import (
                is_external_institution_query,
                is_lightweight_general_query,
                is_operational_institutional_query,
            )
            from backend.app.services.intent_signals import search_query_for_retrieval

            if is_external_institution_query(text) or is_external_institution_query(
                search_text
            ):
                formatted = self._external_institution_reply(
                    text=text,
                    decision=decision,
                    started=started,
                    router_model=router_model,
                )
                yield from _chunk_text(formatted.content, size=48)
                yield formatted
                return
            if is_lightweight_general_query(text) and not is_operational_institutional_query(
                search_text
            ):
                yield from self._maybe_general_educational_stream(
                    text=text,
                    decision=decision,
                    session_context=session_context,
                    started=started,
                    router_model=router_model,
                    history=history,
                )
                return
            search_q = search_query_for_retrieval(search_text)
            yield from self._retrieve_and_generate_stream(
                text=text,
                decision=decision,
                source_label="institutional",
                search_fn=lambda: self._get_kb_service().search_institutional(search_q),
                started=started,
                router_model=router_model,
                history=history,
            )
            return

        if decision.intent == "personal_notes":
            if decision.requires_upload or not session_context.has_notes or not session_id:
                formatted = self._formatter.format_non_retrieval_reply(
                    user_message=text,
                    decision=decision,
                    session_context=session_context,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    router_model=router_model,
                )
                yield from _chunk_text(formatted.content, size=48)
                yield formatted
                return
            yield from self._retrieve_and_generate_stream(
                text=text,
                decision=decision,
                source_label="session notes",
                search_fn=lambda: self._search_session(session_id, search_text),
                started=started,
                router_model=router_model,
                history=history,
            )
            return

        if decision.intent == "out_of_scope":
            rescued = self._try_institutional_rescue(
                text=text,
                decision=decision,
                started=started,
                router_model=router_model,
                history=history,
                retrieval_query=search_text,
            )
            if rescued is not None:
                yield from _chunk_text(rescued.content, size=48)
                yield rescued
                return
            yield from self._maybe_general_educational_stream(
                text=text,
                decision=decision,
                session_context=session_context,
                started=started,
                router_model=router_model,
                history=history,
            )
            return

        formatted = self._formatter.format_non_retrieval_reply(
            user_message=text,
            decision=decision,
            session_context=session_context,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            router_model=router_model,
        )
        yield from _chunk_text(formatted.content, size=48)
        yield formatted

    def _maybe_general_educational_stream(
        self,
        *,
        text: str,
        decision: RouteDecision,
        session_context: SessionContext,
        started: float,
        router_model: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> Iterator[str | Any]:
        from backend.app.services.knowledge_mode_classifier import (
            is_chitchat_query,
            is_educational_query,
            is_external_institution_query,
            is_lightweight_general_query,
            is_operational_institutional_query,
        )

        if is_chitchat_query(text):
            formatted = self._formatter.format_chitchat_reply(
                user_message=text,
                decision=decision,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                router_model=router_model,
            )
            yield from _chunk_text(formatted.content, size=48)
            yield formatted
            return

        if is_external_institution_query(text):
            formatted = self._external_institution_reply(
                text=text,
                decision=decision,
                started=started,
                router_model=router_model,
            )
            yield from _chunk_text(formatted.content, size=48)
            yield formatted
            return

        if is_operational_institutional_query(text):
            knowledge = KnowledgeModeDecision(
                mode="insufficient_institutional_data",
                reason="institution_specific_out_of_scope_no_retrieval",
                retrieval_succeeded=False,
                fallback_used=False,
            )
            generation = self._insufficient_institutional_reply(
                text=text,
                source_label="institutional",
                search_response=SearchResponse(
                    results=[],
                    message="No relevant content found in the institutional knowledge base.",
                ),
                knowledge=knowledge,
            )
            yield from _chunk_text(generation.content, size=48)
            empty = SearchResponse(results=[], message=None)
            built = self._context_builder.build([])
            yield self._formatter.format_generated_reply(
                decision=decision,
                search_response=empty,
                built_context=built,
                generation=generation,
                source_label="institutional",
                search_latency_ms=0.0,
                total_latency_ms=(time.perf_counter() - started) * 1000.0,
                router_model=router_model,
                knowledge_mode="insufficient_institutional_data",
                knowledge_mode_reason=knowledge.reason,
                fallback_used=False,
                retrieval_succeeded=False,
            )
            return

        allow_general = (
            is_educational_query(text) or is_lightweight_general_query(text)
        ) and not is_operational_institutional_query(text)

        if not allow_general:
            formatted = self._formatter.format_non_retrieval_reply(
                user_message=text,
                decision=decision,
                session_context=session_context,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                router_model=router_model,
            )
            yield from _chunk_text(formatted.content, size=48)
            yield formatted
            return

        knowledge = self._knowledge_mode_classifier.decide(
            text,
            has_usable_chunks=False,
        )
        if knowledge.mode != "general_ai":
            knowledge = KnowledgeModeDecision(
                mode="general_ai",
                reason=(
                    "lightweight_general_first_class"
                    if is_lightweight_general_query(text)
                    else "educational_out_of_scope_first_class"
                ),
                retrieval_succeeded=False,
                fallback_used=True,
            )

        generation: GenerationResult | None = None
        for item in self._llm_service.generate_general_stream(
            question=text,
            history=history,
        ):
            if isinstance(item, str):
                yield item
            else:
                generation = item

        if generation is None:
            generation = self._llm_service.generate_general(
                question=text, history=history
            )
            yield from _chunk_text(generation.content, size=48)

        empty = SearchResponse(results=[], message=None)
        built = self._context_builder.build([])
        yield self._formatter.format_generated_reply(
            decision=decision,
            search_response=empty,
            built_context=built,
            generation=generation,
            source_label="general_ai",
            search_latency_ms=0.0,
            total_latency_ms=(time.perf_counter() - started) * 1000.0,
            router_model=router_model,
            knowledge_mode="general_ai",
            knowledge_mode_reason=knowledge.reason,
            fallback_used=True,
            retrieval_succeeded=False,
        )

    def _retrieve_and_generate_stream(
        self,
        *,
        text: str,
        decision: RouteDecision,
        source_label: str,
        search_fn: Any,
        started: float,
        router_model: str,
        history: Sequence[dict[str, str]] | None = None,
    ) -> Iterator[str | Any]:
        search_started = time.perf_counter()
        search_response: SearchResponse = search_fn()
        search_latency_ms = (time.perf_counter() - search_started) * 1000.0
        self._log_search(
            intent=decision.intent,
            search_response=search_response,
            search_latency_ms=search_latency_ms,
        )

        built = self._context_builder.build(search_response.results)
        has_usable = bool(search_response.results) and not built.is_empty
        knowledge = self._knowledge_mode_classifier.decide(
            text,
            has_usable_chunks=has_usable,
        )

        label = (source_label or "").lower()
        if (
            not has_usable
            and knowledge.mode == "general_ai"
            and ("session" in label or "notes" in label)
        ):
            knowledge = KnowledgeModeDecision(
                mode="insufficient_institutional_data",
                reason="personal_notes_without_retrieval",
                retrieval_succeeded=False,
                fallback_used=False,
            )

        from backend.app.services.knowledge_mode_classifier import (
            is_operational_institutional_query,
        )

        if (
            not has_usable
            and knowledge.mode == "general_ai"
            and "institutional" in label
            and is_operational_institutional_query(text)
        ):
            knowledge = KnowledgeModeDecision(
                mode="insufficient_institutional_data",
                reason="institution_specific_no_retrieval",
                retrieval_succeeded=False,
                fallback_used=False,
            )

        generation: GenerationResult | None = None
        if knowledge.mode == "grounded":
            for item in self._llm_service.generate_stream(
                context=built,
                question=text,
                history=history,
            ):
                if isinstance(item, str):
                    yield item
                else:
                    generation = item
        elif knowledge.mode == "general_ai":
            for item in self._llm_service.generate_general_stream(
                question=text,
                history=history,
            ):
                if isinstance(item, str):
                    yield item
                else:
                    generation = item
        else:
            generation = self._insufficient_institutional_reply(
                text=text,
                source_label=source_label,
                search_response=search_response,
                knowledge=knowledge,
            )
            yield from _chunk_text(generation.content, size=48)

        if generation is None:
            generation = GenerationResult(
                content="",
                provider=None,
                model=None,
                latency_ms=0.0,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                selection={"mode": "stream_empty"},
                success=False,
                error="empty_stream",
            )

        yield self._formatter.format_generated_reply(
            decision=decision,
            search_response=search_response,
            built_context=built,
            generation=generation,
            source_label=source_label,
            search_latency_ms=search_latency_ms,
            total_latency_ms=(time.perf_counter() - started) * 1000.0,
            router_model=router_model,
            knowledge_mode=knowledge.mode,
            knowledge_mode_reason=knowledge.reason,
            fallback_used=knowledge.fallback_used,
            retrieval_succeeded=knowledge.retrieval_succeeded,
        )


def _short_quote(text: str, limit: int = 160) -> str:
    cleaned = (text or "").strip().replace("\n", " ")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def _session_query_variants(text: str) -> list[str]:
    """
    Expand session searches for chapter / section / page asks.

    Keeps the original query first, then adds targeted variants so retrieval
    prefers body content over TOC metadata alone.
    """
    raw = (text or "").strip()
    if not raw:
        return [raw]
    variants = [raw]
    chapter = re.search(r"\bchapter\s+(\d+|[ivxlcdm]+)\b", raw, re.IGNORECASE)
    if chapter:
        num = chapter.group(1)
        variants.extend(
            [
                f"Chapter {num}",
                f"Chapter {num} title section heading",
                f"Chapter {num} content summary pages",
                f"Ch. {num}",
            ]
        )
    section = re.search(r"\bsection\s+(\d+(?:\.\d+)*)\b", raw, re.IGNORECASE)
    if section:
        sec = section.group(1)
        variants.extend([f"Section {sec}", f"Section {sec} heading"])
    page = re.search(r"\bpages?\s+(\d+)(?:\s*[-–to]+\s*(\d+))?\b", raw, re.IGNORECASE)
    if page:
        start, end = page.group(1), page.group(2)
        if end:
            variants.append(f"page {start} to {end}")
        else:
            variants.append(f"page {start}")
    # Deduplicate while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for item in variants:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def _looks_like_metadata_only(text: str) -> bool:
    """Heuristic: skip tiny TOC / page-number-only chunks when better hits exist."""
    cleaned = (text or "").strip()
    if not cleaned:
        return True
    if len(cleaned) < 40:
        return True
    lower = cleaned.lower()
    metadata_markers = (
        "table of contents",
        "contents",
        "page no",
        "page number",
        "index",
    )
    if any(m in lower for m in metadata_markers) and len(cleaned) < 180:
        return True
    # Mostly digits / dots / short labels
    alpha = sum(1 for c in cleaned if c.isalpha())
    if alpha < 20:
        return True
    return False


def _chunk_text(text: str, *, size: int = 48) -> Iterator[str]:
    """Soft-chunk non-streamed replies so the UI still feels progressive."""
    content = text or ""
    if not content:
        return
    for i in range(0, len(content), size):
        yield content[i : i + size]


_chat_service: ChatService | None = None


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
