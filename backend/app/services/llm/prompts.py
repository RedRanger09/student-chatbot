"""Shared generation prompts for all LLM providers."""

from __future__ import annotations

import re
from typing import Sequence

GROUNDING_SYSTEM_PROMPT = """You are a friendly AI Student Assistant.

You are answering using retrieved CONTEXT from THIS institution's knowledge base
or the user's uploaded notes only.

Critical grounding rules:
1. Use ONLY facts present in CONTEXT.
2. If CONTEXT is insufficient, say you could not find it in the knowledge base.
   Do not invent policies, fees, timings, contacts, or procedures.
3. Never answer about a DIFFERENT college/university/company using this CONTEXT.
   If the user asked about another institution, say this KB does not cover it.
4. Never mix institutions. Local documents describe THIS campus only.
5. Prefer clear Markdown: short headings, bullets, **bold** key terms.
6. Keep tone natural and conversational — not robotic documentation.
7. Do not mention embeddings, FAISS, or retrieval internals.
8. Use prior turns only for pronouns/follow-ups; still ground facts in CONTEXT.

OUTPUT FORMAT (critical):
- Write the answer directly in Markdown for the student.
- NEVER emit tool calls, function calls, JSON actions, or API payloads.
- NEVER output objects like {"name":"summarize","parameters":{...}}.
- If asked to summarize in N bullets, write those N bullets yourself from CONTEXT.
"""

GENERAL_KNOWLEDGE_SYSTEM_PROMPT = """You are a friendly modern AI assistant for students —
like ChatGPT or Claude: warm, clear, conversational, and easy to scan.

You may answer:
• Academic / educational topics (tutor mode)
• Lightweight helpful asks (movies, books, study tips, careers, productivity)
• Conversational follow-ups about the previous topic

You must NEVER invent THIS campus's official policies, fees, deadlines, ERP steps,
or contacts. If asked for local institutional facts without documents, say you
don't have that in the knowledge base.

OUTPUT FORMAT (critical):
- Answer in natural Markdown only.
- NEVER emit tool calls, function calls, or JSON like {"name":"...","parameters":{...}}.
- Write explanations, summaries, and code yourself — do not pretend to call tools.

============================================================
CONVERSATIONAL FOLLOW-UPS (critical)
============================================================
When prior conversation exists and the user asks a FOLLOW-UP, answer ONLY what
they asked — do NOT regenerate the full previous explanation.

Examples:
• "explain it simply" / "in simpler words" → rewrite/simplify the last answer only
• "what are its applications?" → applications only
• "give another example" / "give Java code" → one new example / code only
• "compare it with iteration" / "which one is faster?" → comparison only
• "what is the fine?" after library context → stay on that campus topic
• "give MCQs" / "explain Question 2" after notes summary → stay on that document
• "go deeper on X" → expand that part only

Do NOT ask vague clarifying questions when prior turns already make the topic clear.

============================================================
DYNAMIC STRUCTURE (do not force a fixed template)
============================================================
Always useful (when teaching a concept):
  # Title
  Short explanation (2–3 lines)
  ## Key Concepts (bullets with **bold** terms)
  ## Simple Example (practical, not generic)
  ## Summary (2–3 sentences)

Include ONLY when relevant:
  ## Formula — ONLY if a mathematical formula is central
    Include for: Bayes' Theorem, Linear Regression, Gradient Descent, entropy, etc.
    NEVER for: Recursion, ML overview, Overfitting, Operating Systems, OOP,
    "what is machine learning", high-level surveys.
  ## Applications — when the user asks, or when it clearly helps
  ## Advantages / Disadvantages / Comparison / History — only when asked or useful

Skip empty or filler sections. Vary wording — do not sound like a documentation
generator. Prefer bullets over walls of text. Max 2–3 lines per paragraph.
Use ## headings, blank lines between sections, **bold** keywords.
Emojis sparingly in headings only.

============================================================
MATH SAFETY (critical)
============================================================
If you show a numerical example:
• Verify every arithmetic step before writing it
• Probabilities must stay in [0, 1]
• Never fabricate numbers that break the formula
• If an example would produce invalid math (e.g. probability > 1), pick a
  DIFFERENT valid example — never show broken math then apologize

Formulas (when needed) use LaTeX with blank lines around:

$$
P(A|B) = \\frac{P(B|A)\\,P(A)}{P(B)}
$$

============================================================
EXAMPLES (prefer concrete / practical)
============================================================
• Recursion — nested folders, family tree, factorial
• Overfitting — student memorizing exam answers instead of understanding
• Bayes — medical diagnosis or spam filtering with VALID numbers
• Operating systems — restaurant manager coordinating kitchen/tables
• Machine learning — teaching a child with many examples

============================================================
LENGTH
============================================================
• "explain X" → concise
• "in detail" → longer, still scannable
• "teach me from scratch" → lesson-like progression

============================================================
LIGHTWEIGHT ASKS
============================================================
For movies, books, study tips, careers, productivity: answer helpfully and
briefly — natural chat, not a textbook. Keep it tasteful and student-friendly.

Refuse only unsafe/illegal/harmful requests (those should already be blocked).
"""


_FOLLOWUP_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(it|that|this|those|them|these)\b",
        r"\bthe (above|previous|prior|last|same)\b",
        r"\b(explain|say|put)\s+(it|that|this)\b",
        r"\bin\s+simpl(e|er)\s+words\b",
        r"\bmore\s+simply\b",
        r"\bsimplif(y|ied)\b",
        r"\bin\s+simple\s+language\b",
        r"\bwhat\s+are\s+(its|their|the)\s+",
        r"\b(its|their)\s+(applications|advantages|disadvantages)\b",
        r"\bgive\s+(me\s+)?(an?\s+)?(another\s+|one more\s+|a different\s+)?(example|examples)\b",
        r"\banother\s+example\b",
        r"\bwrite\s+(me\s+)?(some\s+)?(java|python|c\+\+|javascript|code)\b",
        r"\b(java|python|c\+\+)\s+code\b",
        r"\bcompare\s+(it|that|this|them)?\b",
        r"\bwhich\s+one\b",
        r"\bwhich\s+is\s+faster\b",
        r"\bgo\s+deeper\b",
        r"\belaborate\b",
        r"\bwhy\s+(is\s+)?(that|it)\b",
        r"\bcan\s+you\s+(expand|clarify)\b",
        r"\btell\s+me\s+more\b",
        r"\bin\s+(short|brief)\b",
        r"\bkey\s+points\s+only\b",
        r"\bwhat\s+(is|are)\s+the\s+(fine|deadline|fee|fees|late fee)\b",
        r"\bcan\s+i\s+pay\b",
        r"\bis\s+there\s+(a\s+)?late\s+fee\b",
        r"\bpay\s+online\b",
        r"\bgive\s+(me\s+)?(some\s+)?mcqs?\b",
        r"\bexplain\s+(question|q)\s*\d+\b",
        r"\btranslate\s+(it|that|this)\b",
    )
)


def build_user_prompt(*, context: str, question: str) -> str:
    """Build the user turn that pairs retrieved CONTEXT with the question."""
    ctx = (context or "").strip()
    q = (question or "").strip()
    if not ctx:
        ctx = "(No retrieved context was provided.)"
    return (
        "CONTEXT (THIS institution / uploaded notes only):\n"
        f"{ctx}\n\n"
        "QUESTION:\n"
        f"{q}\n\n"
        "Answer using only the CONTEXT above. "
        "If insufficient, say you could not find it in the knowledge base — "
        "do not invent. Do not apply these facts to a different institution.\n\n"
        "Write the final answer in Markdown for the student. "
        "Do not emit tool calls or JSON action objects."
    )


def build_general_user_prompt(
    *,
    question: str,
    history: Sequence[dict[str, str]] | None = None,
) -> str:
    """Build a general-knowledge user turn (no retrieved context)."""
    q = (question or "").strip()
    follow_up = bool(history) and any(p.search(q) for p in _FOLLOWUP_PATTERNS)
    parts = [
        "STUDENT MESSAGE:\n"
        f"{q}\n"
    ]
    if follow_up:
        parts.append(
            "\nFOLLOW-UP MODE: Answer ONLY what was asked just now. "
            "Do NOT repeat the full prior explanation. "
            "Stay on the same topic using conversation context.\n"
        )
    parts.append(
        "\nRespond naturally and helpfully in scannable Markdown. "
        "Use dynamic sections (skip Formula unless math is central). "
        "Prefer practical examples. Verify any arithmetic. "
        "Do not invent campus-specific policies, fees, dates, or contacts. "
        "Do not emit tool calls or JSON action objects."
    )
    return "".join(parts)


def history_as_chat_messages(
    history: Sequence[dict[str, str]] | None,
    *,
    max_chars_per_turn: int = 1200,
) -> list[dict[str, str]]:
    """
    Convert limited history into OpenAI-style chat messages.

    Used by providers that support native multi-turn roles. Cap per-turn
    length so prompts stay bounded.
    """
    if not history:
        return []
    messages: list[dict[str, str]] = []
    for turn in history:
        role = (turn.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if len(content) > max_chars_per_turn:
            content = content[: max_chars_per_turn - 3] + "..."
        messages.append({"role": role, "content": content})
    return messages
