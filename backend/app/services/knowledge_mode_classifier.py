"""
Hybrid Knowledge Mode classifier (post-retrieval).

Separate from the Intent Router. Runs only after retrieval to decide whether
an empty result set may safely fall back to General AI Knowledge.

Educational detection uses lightweight natural-language heuristics (not only
start-anchored regexes). Operational campus questions never fall back to
General AI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from src.utils.logger import get_logger

logger = get_logger(__name__)

KnowledgeMode = Literal["grounded", "general_ai", "insufficient_institutional_data"]

# Operational campus signals — never invent answers for these.
_OPERATIONAL_INSTITUTIONAL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bhostel\b",
        r"\bmess\b",
        r"\bfee(s)?\b",
        r"\btuition\b",
        r"\brefund\b",
        r"\blate[- ]?fee\b",
        r"\bpayment\b",
        r"\badmission(s)?\b",
        r"\beligibility\b",
        r"\bdeadline\b",
        r"\bschedule\b",
        r"\btiming(s)?\b",
        r"\bopening hours?\b",
        r"\boffice hours?\b",
        r"\bhow (much|many)\b",
        r"\bwhen (is|are|do|does|will)\b",
        r"\bwhere (is|are|do|can)\b",
        r"\berp\b",
        r"\bportal\b",
        r"\bpassword\b",
        r"\blogin\b",
        r"\bbonafide\b",
        r"\btranscript\b",
        r"\bmigration certificate\b",
        r"\bprovisional degree\b",
        r"\brevaluation\b",
        r"\bmalpractice\b",
        r"\bacademic calendar\b",
        r"\battendance\b",
        r"\banti[- ]?ragging\b",
        r"\bcode of conduct\b",
        r"\bgrievance\b",
        r"\bplacement cell\b",
        r"\bemergency contact\b",
        r"\binr\b|\brupees?\b",
        r"\bthis (college|university|campus|institution)\b",
        r"\bour (college|university|campus|hostel|library)\b",
        r"\bofficial\b",
        r"\bapply for\b",
        r"\bscholarships? available\b",
        r"\bscholarship eligibility\b",
        r"\blibrary (timing|hours|rules|fine)\b",
        r"\bborrow\b",
        r"\bexam(ination)? (date|schedule|fee|rule|registration)\b",
        r"\bend[- ]?semester\b",
        r"\bparking\b",
        r"\b(campus|college|university|hostel|mess|library|parking)\s+(policy|rules|regulations)\b",
        r"\bvisitor\s+policy\b",
        r"\bgate\s+pass\b",
        r"\bstudent\s+polic(y|ies)\b",
        r"\bimportant\s+(student\s+)?polic(y|ies)\b",
        r"\bbacklog(s)?\b",
        r"\bcan i graduate\b",
        r"\bgraduate\s+with\b",
        r"\bscholarship(s)?\b",
        r"\blibrary\b",
    )
)

# Softeners stripped before cue matching so conversational asks normalize
# toward the same educational core ("Can you tell me how X works?" → "how X works?").
_POLITE_WRAPPERS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^\s*(can|could|would|will)\s+you\s+(please\s+)?",
        r"^\s*please\s+",
        r"^\s*i\s+(just\s+)?(want|wanted|would\s+like)\s+to\s+"
        r"(know|learn|understand|ask|hear|study)\s+(about\s+|how\s+|what\s+)?",
        r"^\s*i\s+(want|wanted|would\s+like)\s+to\s+learn\b\s*",
        r"^\s*i'?m\s+(curious|wondering)\s+(about\s+|if\s+)?",
        r"^\s*do\s+you\s+(know|mind\s+(explaining|telling|describing))\s+",
        r"^\s*help\s+me\s+(to\s+)?",
    )
)

# Cue phrases / structures that signal educational / explanatory intent.
_EDUCATIONAL_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bwhat\s+(is|are|does|do|was|were)\b",
        r"\bexplain(\s+how|\s+why|\s+what)?\b",
        r"\bdefine\b",
        r"\bdescribe\b",
        r"\bhow\s+does\b",
        r"\bhow\s+do\b",
        r"\bhow\s+.+\bworks?\b",
        r"\bwhy\s+(is|are|do|does|did|would|should)\b",
        r"\btell\s+me\s+(about|how|what|why)\b",
        r"\bteach\s+me\b",
        r"\bhelp\s+me\s+understand\b",
        r"\bgive\s+(me\s+)?(an?\s+)?overview\b",
        r"\bgive\s+(me\s+)?(an?\s+)?(simple\s+)?explanation\b",
        r"\bgive\s+(me\s+)?(an?\s+)?example\b",
        r"\bwalk\s+me\s+through\b",
        r"\bbreak\s+(it|this)\s+down\b",
        r"\boverview\s+of\b",
        r"\bbasics?\s+of\b",
        r"\bintroduction\s+to\b",
        r"\bconcept\s+of\b",
        r"\bmeaning\s+of\b",
        r"\bin\s+simple\s+terms\b",
        r"\bdifference\s+between\b",
        r"\bcompare\b",
        r"\badvantages?\s+of\b",
        r"\bdisadvantages?\s+of\b",
        r"\bpros\s+and\s+cons\b",
        r"\bhow\s+it\s+works\b",
        r"\bworking\s+of\b",
        r"\bfundamentals?\s+of\b",
        r"\bprinciples?\s+of\b",
        # Learning intents ("I want to learn ML", "study OS")
        r"\b(want|wanted|would\s+like)\s+to\s+learn\b",
        r"\blearn(\s+about)?\b",
        r"\bstudy(\s+about)?\b",
        r"\brevise\b",
        r"\bget\s+started\s+with\b",
        r"\bintro(duction)?\s+to\b",
    )
)

# Academic / CS / STEM topic signals — catch topic-only asks after wrappers strip.
_ACADEMIC_TOPIC_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bmachine\s+learning\b",
        r"\bdeep\s+learning\b",
        r"\bartificial\s+intelligence\b",
        r"\bneural\s+networks?\b",
        r"\btransformers?\b",
        r"\bgradient\s+descent\b",
        r"\breinforcement\s+learning\b",
        r"\bdata\s+structures?\b",
        r"\bdsa\b",
        r"\balgorithms?\b",
        r"\bbinary\s+search\b",
        r"\brecursion\b",
        r"\boperating\s+systems?\b",
        r"\bdbms\b",
        r"\bdatabases?\b",
        r"\bsql\b",
        r"\bcomputer\s+networks?\b",
        r"\bcyber\s*security\b",
        r"\binformation\s+security\b",
        r"\boop\b",
        r"\bobject[- ]oriented\b",
        r"\bpython\b",
        r"\bjava\b",
        r"\bc\+\+",
        r"\bjavascript\b",
        r"\btypescript\b",
        r"\bdecorators?\b",
        r"\bcollections?\b",
        r"\bllms?\b",
        r"\blarge\s+language\s+models?\b",
        r"\bprogramming\b",
        r"\bcoding\b",
        r"\bsoftware\s+engineering\b",
        r"\bcalculus\b",
        r"\blinear\s+algebra\b",
        r"\bprobability\b",
        r"\bstatistics\b",
        r"\bcompiler(s)?\b",
        r"\bautomata\b",
        r"\btheory\s+of\s+computation\b",
        r"\bcloud\s+computing\b",
        r"\bdistributed\s+systems?\b",
        r"\bweb\s+development\b",
    )
)

# Strong non-educational intents — only clearly off-mission / unsafe-adjacent.
# Lightweight lifestyle asks (movies, books, study tips) are allowed via General AI.
_NON_EDUCATIONAL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bwho\s+won\b",
        r"\byesterday'?s\b.+\b(match|game|score)\b",
        r"\b(ipl|cricket|football)\s+(match|score|winner|result)\b",
        r"\bwho\s+should\s+i\s+vote\b",
        r"\bbuy\s+(me\s+)?(a\s+)?(gun|weapon|drugs)\b",
    )
)

_PERSONAL_NOTES_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bmy notes\b",
        r"\bmy (upload|document|pdf|file|syllabus)\b",
        r"\buploaded\b",
        r"\baccording to my\b",
        r"\bin the (document|pdf|file) i\b",
    )
)

# Lightweight helpful asks that should use General AI (not refuse).
_LIGHTWEIGHT_GENERAL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\brecommend\b.+\b(movie|film|book|novel|series|show)\b",
        r"\b(movie|film|book)\s+recommendation\b",
        r"\bwhat\s+(movie|book|series)\s+should\s+i\b",
        r"\bstudy\s+tips?\b",
        r"\btime\s+management\b",
        r"\bproductivity\b",
        r"\b(programming|tech|software)\s+career\b",
        r"\bcareer\s+advice\b",
        r"\bhow\s+to\s+prepare\s+for\s+(placements?|interviews?)\b",
        r"\btechnology\s+news\b",
        r"\blearning\s+path\b",
    )
)

# Other colleges/universities — never answer from local institutional KB.
_EXTERNAL_INSTITUTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\biit\b",
        r"\bnit\b",
        r"\biisc\b",
        r"\biiit\b",
        r"\bmit\b",
        r"\bharvard\b",
        r"\bstanford\b",
        r"\boxford\b",
        r"\bcambridge\b",
        r"\bdelhi university\b",
        r"\bjnu\b",
        r"\bbits\s+pilani\b",
        r"\banother (college|university|campus|institution)\b",
        r"\bother (college|university|campus)\b",
    )
)

# Conversational follow-ups that should stay on General AI with prior context.
_CONVERSATIONAL_FOLLOWUP_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(explain|say|put)\s+(it|that|this)\s+(again\s+)?(more\s+)?simpl",
        r"\bin\s+simpl(e|er)\s+words\b",
        r"\bsimplif(y|ied)\b",
        r"\bwhat\s+are\s+(its|their|the)\s+applications\b",
        r"\b(its|their)\s+applications\b",
        r"\bgive\s+(me\s+)?(another|one more|a different)\s+example\b",
        r"\banother\s+example\b",
        r"\bgo\s+deeper\b",
        r"\btell\s+me\s+more\b",
        r"\bin\s+(short|brief)\b",
    )
)


@dataclass(frozen=True)
class KnowledgeModeDecision:
    """Result of the hybrid knowledge-mode classifier."""

    mode: KnowledgeMode
    reason: str
    retrieval_succeeded: bool
    fallback_used: bool


class KnowledgeModeClassifier:
    """
    Decide answer strategy after retrieval.

    When chunks exist → always ``grounded`` (RAG-first).
    When empty → ``general_ai`` only for safe educational questions;
    otherwise ``insufficient_institutional_data``.
    """

    def decide(
        self,
        question: str,
        *,
        has_usable_chunks: bool,
    ) -> KnowledgeModeDecision:
        text = (question or "").strip()
        if has_usable_chunks:
            decision = KnowledgeModeDecision(
                mode="grounded",
                reason="retrieval_hits_available",
                retrieval_succeeded=True,
                fallback_used=False,
            )
            self._log(text, decision)
            return decision

        if not text:
            decision = KnowledgeModeDecision(
                mode="insufficient_institutional_data",
                reason="empty_question",
                retrieval_succeeded=False,
                fallback_used=False,
            )
            self._log(text, decision)
            return decision

        if _matches_any(text, _PERSONAL_NOTES_PATTERNS):
            decision = KnowledgeModeDecision(
                mode="insufficient_institutional_data",
                reason="personal_notes_without_retrieval",
                retrieval_succeeded=False,
                fallback_used=False,
            )
            self._log(text, decision)
            return decision

        # Never invent another institution's facts from empty local retrieval.
        if is_external_institution_query(text):
            decision = KnowledgeModeDecision(
                mode="insufficient_institutional_data",
                reason="external_institution_no_local_kb",
                retrieval_succeeded=False,
                fallback_used=False,
            )
            self._log(text, decision)
            return decision

        operational = is_operational_institutional_query(text)
        educational = is_educational_query(text)
        lightweight = is_lightweight_general_query(text)

        # Definitional educational questions may mention campus topics as concepts
        # (e.g. "What is a scholarship?") — allow general AI unless operational.
        if (educational or lightweight) and not operational:
            decision = KnowledgeModeDecision(
                mode="general_ai",
                reason=(
                    "lightweight_general_no_retrieval"
                    if lightweight and not educational
                    else "educational_query_no_retrieval"
                ),
                retrieval_succeeded=False,
                fallback_used=True,
            )
            self._log(text, decision)
            return decision

        if operational:
            decision = KnowledgeModeDecision(
                mode="insufficient_institutional_data",
                reason="institution_specific_no_retrieval",
                retrieval_succeeded=False,
                fallback_used=False,
            )
            self._log(text, decision)
            return decision

        decision = KnowledgeModeDecision(
            mode="insufficient_institutional_data",
            reason="ambiguous_no_retrieval_safe_default",
            retrieval_succeeded=False,
            fallback_used=False,
        )
        self._log(text, decision)
        return decision

    @staticmethod
    def _log(question: str, decision: KnowledgeModeDecision) -> None:
        logger.info(
            "KnowledgeModeClassifier | mode=%s | retrieval_succeeded=%s | "
            "fallback_used=%s | reason=%s | query=%r",
            decision.mode,
            decision.retrieval_succeeded,
            decision.fallback_used,
            decision.reason,
            (question or "")[:200],
        )


def is_educational_query(question: str) -> bool:
    """
    True when the question looks like a general educational / explanatory ask.

    Uses lightweight heuristics:
      1. Reject clear unsafe / off-mission asks.
      2. Strip polite conversational wrappers ("Can you…", "Please…").
      3. Match educational cue phrases on both raw and normalized text.
      4. Match academic topic keywords (ML, DSA, OS, DBMS, …).
      5. Accept "how <topic> work(s)" / teach / explain structures.
      6. Accept conversational follow-ups about a prior lesson.
    """
    text = (question or "").strip()
    if not text:
        return False
    if _matches_any(text, _NON_EDUCATIONAL_PATTERNS):
        return False
    if is_conversational_followup(text):
        return True

    normalized = _normalize_for_education(text)
    if _has_educational_cue(text) or _has_educational_cue(normalized):
        return True

    # Topic keywords alone count when the user is clearly in study mode
    # (e.g. "I want to learn Machine Learning." → normalized "Machine Learning").
    if _matches_any(text, _ACADEMIC_TOPIC_PATTERNS) or _matches_any(
        normalized, _ACADEMIC_TOPIC_PATTERNS
    ):
        return True

    # Extra structure: imperative teaching verbs near a topic noun phrase.
    if re.search(
        r"\b(explain|describe|define|teach|clarify|learn|study)\b.{0,80}\b\w{2,}\b",
        normalized,
        re.IGNORECASE,
    ):
        return True

    return False


def is_operational_institutional_query(question: str) -> bool:
    """True when the question asks for campus-specific operational facts."""
    return _matches_any((question or "").strip(), _OPERATIONAL_INSTITUTIONAL_PATTERNS)


def is_lightweight_general_query(question: str) -> bool:
    """True for movies/books/careers/study tips — answer via General AI, not refuse."""
    return _matches_any((question or "").strip(), _LIGHTWEIGHT_GENERAL_PATTERNS)


def is_external_institution_query(question: str) -> bool:
    """
    True when the user asks about another college/university/company.

    Local institutional RAG must never answer these from this campus's KB.
    """
    return _matches_any((question or "").strip(), _EXTERNAL_INSTITUTION_PATTERNS)


def is_conversational_followup(question: str) -> bool:
    """True for short follow-ups that should reuse prior topic context."""
    return _matches_any((question or "").strip(), _CONVERSATIONAL_FOLLOWUP_PATTERNS)


_GREETING_PATTERN = re.compile(
    r"^\s*("
    r"hi|hey|hello|hola|namaste|good\s*(morning|afternoon|evening)|"
    r"howdy|yo|sup|hiya|heya|"
    r"hi\s+there|hey\s+there|hello\s+there|"
    r"good\s+day|greetings"
    r")[\s!.?,]*$"
    r"|^\s*(hi|hey|hello)\s*[!.?]*\s*$",
    re.IGNORECASE,
)

_CHITCHAT_PATTERN = re.compile(
    r"^\s*("
    r"hi|hey|hello|hola|namaste|howdy|yo|sup|hiya|heya|"
    r"good\s*(morning|afternoon|evening|day)|greetings|"
    r"hi\s+there|hey\s+there|hello\s+there|"
    r"how\s+are\s+you(\s+doing)?|"
    r"how'?s\s+it\s+going|"
    r"what'?s\s+up|"
    r"who\s+are\s+you|"
    r"what\s+(can|do)\s+you\s+do|"
    r"what\s+are\s+you|"
    r"thanks?(?:\s+you)?|thx|ty|"
    r"bye|goodbye|good\s*bye|see\s+you|cya|"
    r"nice\s+to\s+meet\s+you|"
    r"ok(ay)?|cool|great|awesome|got\s+it"
    r")[\s!.?,]*$",
    re.IGNORECASE,
)


def is_greeting_query(question: str) -> bool:
    """True for short social greetings (hi/hey/hello) — not topic questions."""
    text = (question or "").strip()
    if not text or len(text) > 48:
        return False
    return bool(_GREETING_PATTERN.match(text))


def is_chitchat_query(question: str) -> bool:
    """
    True for lightweight conversation (greetings, thanks, how are you, goodbye).

    These should never hit the academic refuse path.
    """
    text = (question or "").strip()
    if not text or len(text) > 64:
        return False
    return bool(_CHITCHAT_PATTERN.match(text)) or is_greeting_query(text)


def _normalize_for_education(text: str) -> str:
    """
    Peel conversational wrappers so cue matching sees the educational core.

    Example:
      "Can you tell me how LLMs work?" → "tell me how LLMs work?"
    """
    cleaned = (text or "").strip()
    cleaned = re.sub(r"[?!.,:;]+$", "", cleaned).strip()
    for _ in range(4):
        next_text = cleaned
        for wrapper in _POLITE_WRAPPERS:
            next_text = wrapper.sub("", next_text).strip()
        if next_text == cleaned:
            break
        cleaned = next_text
    return cleaned


def _has_educational_cue(text: str) -> bool:
    return _matches_any(text, _EDUCATIONAL_CUE_PATTERNS)


def _matches_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(p.search(text) for p in patterns)
