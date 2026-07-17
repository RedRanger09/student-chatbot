"""
Multi-turn context resolution for follow-up questions.

Expands elliptical follow-ups ("give an example", "what is the fine?")
with the active topic from recent history so routing and retrieval stay
on-topic. Generation still receives the original user text + history.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from backend.app.services.query_normalization import normalize_query
from src.utils.logger import get_logger

logger = get_logger(__name__)

_FOLLOWUP_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(it|that|this|those|them|these)\b",
        r"\bthe (above|previous|prior|last|same)\b",
        r"\b(previous|prior|last) (answer|response|explanation|one)\b",
        r"\bthe (formula|policy|chapter|topic|concept|code|example)\b",
        r"\bgive\s+(me\s+)?(an?\s+)?(another\s+|one more\s+|a different\s+)?(example|examples)\b",
        r"\banother\s+example\b",
        r"\b(explain|say|put)\s+(it|that|this)\b",
        r"\bin\s+simpl(e|er)\s+words\b",
        r"\bsimplif(y|ied)\b",
        r"\bwrite\s+(me\s+)?(some\s+)?(java|python|c\+\+|javascript|code)\b",
        r"\b(java|python|c\+\+)\s+code\b",
        r"\bcompare\s+(it|that|this|them)?\b",
        r"\bwhich\s+one\b",
        r"\bwhich\s+is\s+faster\b",
        r"\bwhat\s+are\s+(its|their|the)\s+",
        r"\b(its|their)\s+(applications|advantages|disadvantages)\b",
        r"\btell\s+me\s+more\b",
        r"\bgo\s+deeper\b",
        r"\belaborate\b",
        r"\bwhat\s+(is|are)\s+the\s+(fine|deadline|fee|fees|late fee)\b",
        r"\bcan\s+i\s+pay\b",
        r"\bis\s+there\s+(a\s+)?late\s+fee\b",
        r"\bpay\s+online\b",
        r"\bgive\s+(me\s+)?(some\s+)?mcqs?\b",
        r"\bexplain\s+(question|q)\s*\d+\b",
        r"\bexplain\s+the\s+(second|first|third|next|previous)\s+topic\b",
        r"\btranslate\s+(it|that|this)\b",
        r"\bin\s+simple\s+language\b",
        r"\bcan\s+faculty\b",
        r"\bmore\s+books\b",
        r"^\s*(and|also|ok|okay|yes|no)[,?]?\s+",
    )
)

_TOPIC_EXTRACT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(?:explain|describe|define|teach|clarify)\s+(.+?)(?:\?|$)",
        r"\b(?:what is|what's|whats)\s+(.+?)(?:\?|$)",
        r"\b(?:tell me about|about)\s+(.+?)(?:\?|$)",
        r"\b(?:summarize|summarise)\s+(.+?)(?:\?|$)",
        r"\b(?:how (?:do|does|can|to))\s+(.+?)(?:\?|$)",
    )
)

_NOTES_CUES = re.compile(
    r"\b(chapter\s+\d+|my notes|uploaded|upload|my (pdf|document|file)|mcqs?|page\s+\d+)\b",
    re.IGNORECASE,
)

_INSTITUTIONAL_TOPIC_CUES = re.compile(
    r"\b(hostel|library|fee|fees|mess|exam|scholarship|attendance|transcript|"
    r"erp|portal|borrowing|fine|deadline|policy|policies|parking)\b",
    re.IGNORECASE,
)

_NEW_TOPIC_STARTERS = re.compile(
    r"^\s*(explain|what is|what's|tell me about|how (do|does|can|to)|summarize|summarise)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ResolvedContext:
    """Outcome of resolving the current user turn against recent history."""

    original: str
    expanded_query: str
    is_followup: bool
    resolved_topic: str | None
    topic_switched: bool
    prior_domain: str | None  # educational | institutional | notes | None
    history_turns_used: int
    reason: str

    def to_log_dict(self) -> dict[str, object]:
        return {
            "original": (self.original or "")[:160],
            "expanded_query": (self.expanded_query or "")[:160],
            "is_followup": self.is_followup,
            "resolved_topic": self.resolved_topic,
            "topic_switched": self.topic_switched,
            "prior_domain": self.prior_domain,
            "history_turns_used": self.history_turns_used,
            "reason": self.reason,
        }


def resolve_followup_context(
    message: str,
    history: Sequence[dict[str, str]] | None,
) -> ResolvedContext:
    """
    Resolve pronouns / elliptical follow-ups using recent conversation turns.

    Returns an expanded query for routing & retrieval. The original message
    should still be sent to the LLM with history.
    """
    original = (message or "").strip()
    turns = _usable_history(history)
    if not original:
        return ResolvedContext(
            original="",
            expanded_query="",
            is_followup=False,
            resolved_topic=None,
            topic_switched=False,
            prior_domain=None,
            history_turns_used=0,
            reason="empty",
        )

    if not turns:
        return ResolvedContext(
            original=original,
            expanded_query=original,
            is_followup=False,
            resolved_topic=None,
            topic_switched=False,
            prior_domain=None,
            history_turns_used=0,
            reason="no_history",
        )

    topic = _extract_active_topic(turns)
    prior_domain = _infer_prior_domain(turns, topic)
    followup = _looks_like_followup(original)

    # Brand-new standalone topic question → do not force prior context.
    if _looks_like_topic_switch(original, topic):
        result = ResolvedContext(
            original=original,
            expanded_query=original,
            is_followup=False,
            resolved_topic=topic,
            topic_switched=True,
            prior_domain=prior_domain,
            history_turns_used=len(turns),
            reason="topic_switch",
        )
        logger.info("ContextResolution | %s", result.to_log_dict())
        return result

    if followup and topic:
        expanded = _expand_with_topic(original, topic)
        result = ResolvedContext(
            original=original,
            expanded_query=expanded,
            is_followup=True,
            resolved_topic=topic,
            topic_switched=False,
            prior_domain=prior_domain,
            history_turns_used=len(turns),
            reason="followup_expanded",
        )
        logger.info("ContextResolution | %s", result.to_log_dict())
        return result

    if followup and not topic:
        result = ResolvedContext(
            original=original,
            expanded_query=original,
            is_followup=True,
            resolved_topic=None,
            topic_switched=False,
            prior_domain=prior_domain,
            history_turns_used=len(turns),
            reason="followup_no_topic",
        )
        logger.info("ContextResolution | %s", result.to_log_dict())
        return result

    result = ResolvedContext(
        original=original,
        expanded_query=original,
        is_followup=False,
        resolved_topic=topic,
        topic_switched=False,
        prior_domain=prior_domain,
        history_turns_used=len(turns),
        reason="standalone",
    )
    logger.info("ContextResolution | %s", result.to_log_dict())
    return result


def select_history_for_prompt(
    history: Sequence[dict[str, str]] | None,
    *,
    resolved: ResolvedContext | None = None,
    max_turns: int | None = None,
) -> list[dict[str, str]]:
    """
    Choose a compact history window for LLM injection.

    On topic switch, keep only the last 2 turns to avoid stale context.
    """
    turns = _usable_history(history)
    if not turns:
        return []
    if resolved and resolved.topic_switched:
        window = turns[-2:]
    elif max_turns is not None:
        window = turns[-max(0, int(max_turns)) :]
    else:
        window = turns
    return [{"role": t["role"], "content": t["content"]} for t in window]


def _usable_history(history: Sequence[dict[str, str]] | None) -> list[dict[str, str]]:
    if not history:
        return []
    cleaned: list[dict[str, str]] = []
    for turn in history:
        role = (turn.get("role") or "").strip().lower()
        content = (turn.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        cleaned.append({"role": role, "content": content})
    return cleaned


def _looks_like_followup(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if any(p.search(cleaned) for p in _FOLLOWUP_PATTERNS):
        return True
    # Short elliptical asks without a clear "explain X" structure.
    if len(cleaned) <= 64 and not _NEW_TOPIC_STARTERS.search(cleaned):
        if re.search(
            r"\b(example|code|fine|deadline|fee|mcq|compare|faster|online|faculty)\b",
            cleaned,
            re.IGNORECASE,
        ):
            return True
    return False


def _looks_like_topic_switch(current: str, prior_topic: str | None) -> bool:
    """True when the user clearly starts a new standalone topic."""
    if not prior_topic:
        return False
    if not _NEW_TOPIC_STARTERS.search(current or ""):
        return False
    if _looks_like_followup(current):
        return False
    current_topic = _extract_topic_from_text(current)
    if not current_topic:
        return False
    prior_n = normalize_query(prior_topic)
    curr_n = normalize_query(current_topic)
    if not prior_n or not curr_n:
        return False
    if prior_n in curr_n or curr_n in prior_n:
        return False
    # Distinct contentful topics.
    prior_tokens = set(prior_n.split())
    curr_tokens = set(curr_n.split())
    overlap = prior_tokens & curr_tokens
    return len(overlap) == 0


def _extract_active_topic(turns: list[dict[str, str]]) -> str | None:
    """Walk backward through user turns until a substantive topic is found."""
    for turn in reversed(turns):
        if turn["role"] != "user":
            continue
        text = turn["content"]
        if _looks_like_followup(text) and len(text) < 100:
            continue
        topic = _extract_topic_from_text(text)
        if topic:
            return topic
    # Fallback: first line of last assistant reply title-like content.
    for turn in reversed(turns):
        if turn["role"] != "assistant":
            continue
        heading = re.search(r"^#\s+(.+)$", turn["content"], re.MULTILINE)
        if heading:
            return _clean_topic(heading.group(1))
        break
    return None


def _extract_topic_from_text(text: str) -> str | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    for pattern in _TOPIC_EXTRACT_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            topic = _clean_topic(match.group(1))
            if topic and len(topic) >= 2:
                return topic
    # Short standalone noun phrases ("Hostel fees", "Chapter 3").
    if len(cleaned) <= 80 and not cleaned.lower().startswith(("hi", "hello", "thanks")):
        return _clean_topic(cleaned)
    return None


def _clean_topic(text: str) -> str:
    topic = (text or "").strip()
    topic = re.sub(r"[?!.,:;]+$", "", topic).strip()
    topic = re.sub(
        r"^(about|regarding|on|the topic of)\s+",
        "",
        topic,
        flags=re.IGNORECASE,
    ).strip()
    # Drop trailing filler.
    topic = re.sub(
        r"\s+(in (simple|detail|depth)|please|for me)$",
        "",
        topic,
        flags=re.IGNORECASE,
    ).strip()
    if len(topic) > 120:
        topic = topic[:117].rstrip() + "..."
    return topic


def _infer_prior_domain(
    turns: list[dict[str, str]],
    topic: str | None,
) -> str | None:
    blob = " ".join(t["content"] for t in turns[-4:] if t["role"] == "user")
    if topic:
        blob = f"{blob} {topic}"
    if _NOTES_CUES.search(blob):
        return "notes"
    if _INSTITUTIONAL_TOPIC_CUES.search(blob):
        return "institutional"
    if topic:
        return "educational"
    return None


def _expand_with_topic(message: str, topic: str) -> str:
    """Attach the active topic so routers/retrievers see the referent."""
    msg = (message or "").strip()
    top = (topic or "").strip()
    if not top:
        return msg
    # Already mentions the topic.
    if normalize_query(top) and normalize_query(top) in normalize_query(msg):
        return msg

    lower = msg.lower()
    # Normalize trailing punctuation before appending phrases.
    base = re.sub(r"[.?!]+$", "", msg).strip()

    if re.search(r"\b(example|examples)\b", lower):
        return f"{base} about {top}"
    if re.search(r"\b(java|python|c\+\+|javascript)\b.*\bcode\b|\bcode\b", lower):
        return f"{base} for {top}"
    if re.search(r"\bcompare\b", lower):
        return f"{base} regarding {top}"
    if re.search(r"\b(fine|deadline|late fee|pay online|faculty)\b", lower):
        return f"{base} (context: {top})"
    if re.search(r"\bmcqs?\b", lower):
        return f"{base} from {top}"
    if re.search(r"\bquestion\s*\d+\b", lower):
        return f"{base} in {top}"
    if re.search(r"\b(it|that|this|those|them)\b", lower):
        # Light pronoun rewrite for routing only.
        rewritten = re.sub(
            r"\b(it|that|this)\b",
            top,
            msg,
            count=1,
            flags=re.IGNORECASE,
        )
        if rewritten.lower() != lower:
            return rewritten
    return f"{base} (about {top})"
