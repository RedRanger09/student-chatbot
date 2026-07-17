"""
Intent signal scoring — synonyms, fuzzy tokens, confidence.

Used by IntentRouter (local scoring + Gemini override) and ChatService
(retrieval-before-fallback rescue). Keeps maps modular and extensible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from backend.app.services.query_normalization import normalize_query

# Topic → synonym / related phrases (institutional campus domain).
TOPIC_SYNONYMS: dict[str, tuple[str, ...]] = {
    "attendance": (
        "attendance",
        "attendence",
        "presence",
        "75 percent",
        "75%",
        "minimum attendance",
        "attendance criteria",
        "attendance requirement",
        "short attendance",
    ),
    "transcript": (
        "transcript",
        "transript",
        "marksheet",
        "mark sheet",
        "academic transcript",
        "official transcript",
        "academic record",
        "grade sheet",
    ),
    "library": (
        "library",
        "libary",
        "books",
        "reading room",
        "digital resources",
        "borrowing",
        "circulation",
        "library timing",
        "library timings",
        "library hours",
    ),
    "hostel": (
        "hostel",
        "accommodation",
        "accomodation",
        "mess",
        "residence",
        "room allocation",
        "hostel fees",
        "hostel fee",
        "hostel rules",
    ),
    "fees": (
        "fee",
        "fees",
        "tuition",
        "payment",
        "semester fees",
        "dues",
        "late fee",
        "refund",
        "hostel fees",
    ),
    "scholarship": (
        "scholarship",
        "scholership",
        "scholarships",
        "financial aid",
        "fee waiver",
        "merit scholarship",
    ),
    "exam": (
        "exam",
        "exams",
        "examination",
        "examinations",
        "revaluation",
        "malpractice",
        "exam form",
        "examination registration",
        "end semester",
        "mid semester",
    ),
    "academic_calendar": (
        "academic calendar",
        "acadmic calendar",
        "academic calender",
        "semester schedule",
        "important dates",
        "college calendar",
    ),
    "policy": (
        "policy",
        "policies",
        "student policy",
        "student policies",
        "code of conduct",
        "disciplinary",
        "rules and regulations",
        "campus policy",
        "college policy",
        "university policy",
    ),
    "backlog": (
        "backlog",
        "backlogs",
        "arrear",
        "arrears",
        "failed subjects",
        "failed subject",
        "carry over",
        "kt",
    ),
    "graduation": (
        "graduate",
        "graduation",
        "convocation",
        "degree completion",
        "eligible to graduate",
        "can i graduate",
    ),
    "certificate": (
        "certificate",
        "bonafide",
        "migration",
        "provisional degree",
        "degree certificate",
    ),
    "erp": (
        "erp",
        "student portal",
        "campus portal",
        "password reset",
        "login issue",
    ),
    "admission": (
        "admission",
        "admissions",
        "apply for admission",
        "enrolment",
        "enrollment",
    ),
    "wifi": (
        "wi-fi",
        "wifi",
        "campus network",
        "internet access",
    ),
    "placement": (
        "placement",
        "placements",
        "campus drive",
        "internship cell",
    ),
    "counseling": (
        "counseling",
        "counselling",
        "student counselor",
        "wellness cell",
    ),
    "grievance": (
        "grievance",
        "complaint",
        "redressal",
    ),
    "parking": (
        "parking",
        "vehicle pass",
        "campus parking",
    ),
    "onboarding": (
        "onboarding",
        "orientation",
        "fresher",
        "new student",
    ),
}

_PERSONAL_NOTES_CUES: tuple[str, ...] = (
    "my notes",
    "my note",
    "uploaded",
    "upload",
    "my document",
    "my pdf",
    "my file",
    "according to my notes",
    "summarize my",
    "summarise my",
    "from my notes",
    "in my notes",
    "chapter from my",
)

_ESCALATION_CUES: tuple[str, ...] = (
    "hurt myself",
    "kill myself",
    "suicide",
    "self harm",
    "self-harm",
    "want to die",
    "harass",
    "harassment",
    "bully",
    "bullied",
    "assault",
    "medical emergency",
    "make a bomb",
    "build a bomb",
)

# Strong educational concept cues (prefer General AI when dominant).
_EDUCATIONAL_CUES: tuple[str, ...] = (
    "recursion",
    "overfitting",
    "machine learning",
    "gradient descent",
    "bayes",
    "neural network",
    "linked list",
    "binary tree",
    "operating system concept",
    "what is polymorphism",
    "explain dsa",
    "teach me",
    "from scratch",
)

_FUZZY_VOCAB: tuple[str, ...] = tuple(
    sorted(
        {
            word
            for phrases in TOPIC_SYNONYMS.values()
            for phrase in phrases
            for word in phrase.split()
            if len(word) >= 4
        }
        | {
            "college",
            "university",
            "department",
            "professor",
            "semester",
            "student",
            "campus",
            "scholarship",
            "attendance",
            "transcript",
            "library",
            "hostel",
            "calendar",
            "examination",
            "backlog",
            "graduate",
            "graduation",
            "policy",
            "policies",
        }
    )
)


@dataclass(frozen=True)
class IntentScores:
    """Confidence-style scores in [0, 1] for each routing family."""

    institutional: float
    personal_notes: float
    escalate: float
    educational: float
    matched_topics: tuple[str, ...]
    matched_terms: tuple[str, ...]

    def dominant_route(self) -> str:
        """Return the highest-scoring non-educational family label."""
        ranked = [
            ("escalate", self.escalate),
            ("personal_notes", self.personal_notes),
            ("institutional_faq", self.institutional),
            ("out_of_scope", self.educational),
        ]
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked[0][0]


def score_intents(query: str) -> IntentScores:
    """Score routing families from a raw or already-normalized query."""
    normalized = normalize_query(query)
    if not normalized:
        return IntentScores(0.0, 0.0, 0.0, 0.0, (), ())

    fuzzy_hits = _fuzzy_expand_tokens(normalized)
    haystack = f"{normalized} {' '.join(fuzzy_hits)}".strip()

    matched_topics: list[str] = []
    matched_terms: list[str] = []
    topic_hits = 0
    for topic, phrases in TOPIC_SYNONYMS.items():
        hit = _best_phrase_hit(haystack, phrases)
        if hit:
            matched_topics.append(topic)
            matched_terms.append(hit)
            topic_hits += 1

    institutional = min(1.0, 0.22 * topic_hits)
    # Boost high-signal campus phrases.
    boost_phrases = (
        "student policies",
        "student policy",
        "college library",
        "university library",
        "hostel fees",
        "can i graduate",
        "graduate with backlog",
        "graduate if",
        "attendance criteria",
        "minimum attendance",
        "important policies",
        "campus rules",
        "library timings",
        "library timing",
        "when are exams",
        "when is the exam",
    )
    for phrase in boost_phrases:
        if phrase in haystack:
            institutional = min(1.0, institutional + 0.28)
            matched_terms.append(phrase)

    if any(token in haystack for token in ("policy", "policies", "backlog", "backlogs")):
        institutional = min(1.0, institutional + 0.18)
    if "library" in haystack or "hostel" in haystack:
        institutional = min(1.0, institutional + 0.12)
    if re.search(r"\b(fee|fees|transcript|scholarship|attendance|exam|exams|semester)\b", haystack):
        institutional = min(1.0, institutional + 0.15)
    if "exam" in matched_topics:
        institutional = min(1.0, institutional + 0.2)

    personal = 0.0
    for cue in _PERSONAL_NOTES_CUES:
        if cue in haystack:
            personal = max(personal, 0.72 if "my " in cue or "upload" in cue else 0.55)
            matched_terms.append(cue)

    escalate = 0.0
    for cue in _ESCALATION_CUES:
        if cue in haystack:
            escalate = max(escalate, 0.85)
            matched_terms.append(cue)

    educational = 0.0
    for cue in _EDUCATIONAL_CUES:
        if cue in haystack:
            educational = max(educational, 0.7)
            matched_terms.append(cue)
    if re.search(
        r"\b(explain|teach|what is|how does|define)\b.{0,40}\b(recursion|algorithm|overfitting|entropy|gradient|bayes|oop|polymorphism)\b",
        haystack,
    ):
        educational = max(educational, 0.75)

    # Mixed campus + concept questions: keep campus as dominant when a topic hit.
    if matched_topics and educational >= 0.55:
        institutional = max(institutional, 0.55)

    return IntentScores(
        institutional=round(institutional, 3),
        personal_notes=round(personal, 3),
        escalate=round(escalate, 3),
        educational=round(educational, 3),
        matched_topics=tuple(matched_topics),
        matched_terms=tuple(dict.fromkeys(matched_terms)),
    )


def institutional_confidence(query: str) -> float:
    return score_intents(query).institutional


def should_prefer_institutional(query: str, *, min_score: float = 0.42) -> bool:
    scores = score_intents(query)
    if scores.escalate >= 0.7:
        return False
    if scores.personal_notes >= 0.65:
        return False
    if scores.institutional < min_score:
        return False
    # Prefer institutional unless educational clearly dominates.
    if scores.educational >= scores.institutional + 0.25:
        return False
    return True


def should_try_institutional_retrieval(query: str) -> bool:
    """
    True when routing is uncertain but campus retrieval is worth attempting
    before falling back to General AI.
    """
    scores = score_intents(query)
    if scores.escalate >= 0.7 or scores.personal_notes >= 0.65:
        return False
    if scores.institutional >= 0.28 and scores.institutional + 0.08 >= scores.educational:
        return True
    return False


def search_query_for_retrieval(query: str) -> str:
    """Prefer normalized text for institutional / notes search."""
    normalized = normalize_query(query)
    return normalized or (query or "").strip()


def _best_phrase_hit(haystack: str, phrases: Iterable[str]) -> str | None:
    for phrase in sorted(phrases, key=len, reverse=True):
        if phrase in haystack:
            return phrase
        # Fuzzy single-token phrases only.
        if " " not in phrase and len(phrase) >= 5:
            for token in haystack.split():
                if _similarity(token, phrase) >= 0.84:
                    return phrase
    return None


def _fuzzy_expand_tokens(normalized: str) -> list[str]:
    expanded: list[str] = []
    for token in normalized.split():
        if len(token) < 4:
            continue
        if token in _FUZZY_VOCAB:
            continue
        best = None
        best_score = 0.0
        for vocab in _FUZZY_VOCAB:
            score = _similarity(token, vocab)
            if score > best_score:
                best_score = score
                best = vocab
        if best and best_score >= 0.84:
            expanded.append(best)
    return expanded


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()
