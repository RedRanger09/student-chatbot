"""
Rule-based follow-up suggestion generator.

Produces 3–5 chips after a completed assistant reply. Designed so an
LLM-backed generator can replace ``suggest_followups`` later without
changing the metadata contract.
"""

from __future__ import annotations

import re
from typing import Any


# Topic → suggested follow-up prompts (label shown on chip may match prompt).
_TOPIC_SUGGESTIONS: dict[str, list[dict[str, str]]] = {
    "machine_learning": [
        {"label": "Supervised Learning", "prompt": "What is supervised learning?"},
        {"label": "Unsupervised Learning", "prompt": "What is unsupervised learning?"},
        {"label": "Deep Learning", "prompt": "What is deep learning?"},
        {"label": "Overfitting", "prompt": "Explain overfitting in machine learning."},
        {"label": "Applications", "prompt": "What are the applications of machine learning?"},
    ],
    "recursion": [
        {"label": "Base Case", "prompt": "What is a base case in recursion?"},
        {"label": "Recursion vs Iteration", "prompt": "What is the difference between recursion and iteration?"},
        {"label": "Call Stack", "prompt": "How does the call stack work with recursion?"},
        {"label": "Example", "prompt": "Give a simple example of recursion in programming."},
    ],
    "oop": [
        {"label": "Encapsulation", "prompt": "What is encapsulation in OOP?"},
        {"label": "Inheritance", "prompt": "What is inheritance in object-oriented programming?"},
        {"label": "Polymorphism", "prompt": "Explain polymorphism with a simple example."},
        {"label": "Abstraction", "prompt": "What is abstraction in OOP?"},
    ],
    "networking": [
        {"label": "DNS", "prompt": "What is DNS?"},
        {"label": "HTTP vs HTTPS", "prompt": "What is the difference between HTTP and HTTPS?"},
        {"label": "TCP/IP", "prompt": "Explain TCP/IP in simple terms."},
        {"label": "IP Address", "prompt": "What is an IP address?"},
    ],
    "fees": [
        {"label": "Refund Policy", "prompt": "What is the refund policy for tuition fees?"},
        {"label": "Hostel Fees", "prompt": "What is the hostel fee?"},
        {"label": "Payment Methods", "prompt": "How do I pay my tuition fees?"},
        {"label": "Late Fee", "prompt": "Is there a late fee for delayed payments?"},
    ],
    "hostel": [
        {"label": "Hostel Fees", "prompt": "What is the hostel fee?"},
        {"label": "Mess Timings", "prompt": "What are the mess timings?"},
        {"label": "Hostel Rules", "prompt": "What are the hostel rules?"},
        {"label": "Room Allotment", "prompt": "How does hostel room allotment work?"},
    ],
    "admissions": [
        {"label": "Eligibility", "prompt": "What is the eligibility criteria for admission?"},
        {"label": "Documents Required", "prompt": "What documents are required for admission?"},
        {"label": "Application Timeline", "prompt": "What is the application timeline for admissions?"},
        {"label": "Scholarships", "prompt": "What scholarships are available?"},
    ],
    "library": [
        {"label": "Library Timings", "prompt": "What are the library timings?"},
        {"label": "Borrowing Rules", "prompt": "What are the library borrowing rules?"},
        {"label": "Library Fine", "prompt": "What is the library fine policy?"},
        {"label": "Digital Resources", "prompt": "Does the library provide digital resources?"},
    ],
    "exams": [
        {"label": "Exam Schedule", "prompt": "Where can I find the exam schedule?"},
        {"label": "Revaluation", "prompt": "How do I apply for revaluation?"},
        {"label": "Hall Ticket", "prompt": "How do I download my hall ticket?"},
        {"label": "Malpractice Rules", "prompt": "What are the exam malpractice rules?"},
    ],
    "general_edu": [
        {"label": "Simple Example", "prompt": "Can you give a simple example?"},
        {"label": "Key Concepts", "prompt": "What are the key concepts I should remember?"},
        {"label": "Common Mistakes", "prompt": "What are common mistakes students make with this topic?"},
        {"label": "Related Topic", "prompt": "What should I learn next related to this?"},
    ],
    "greeting": [
        {"label": "Tuition Fees", "prompt": "How do I pay my tuition fees?"},
        {"label": "Hostel Info", "prompt": "What is the hostel fee?"},
        {"label": "Library Hours", "prompt": "What are the library timings?"},
        {"label": "What is ML?", "prompt": "What is machine learning?"},
    ],
    "campus_general": [
        {"label": "Scholarships", "prompt": "What scholarships are available?"},
        {"label": "Hostel Info", "prompt": "Tell me about hostel facilities."},
        {"label": "Library Hours", "prompt": "What are the library timings?"},
        {"label": "Fee Payment", "prompt": "How do I pay my tuition fees?"},
    ],
}

_TOPIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("machine_learning", re.compile(
        r"\b(machine learning|supervised learning|unsupervised learning|"
        r"deep learning|neural network|overfitting|underfitting|gradient descent)\b",
        re.I,
    )),
    ("recursion", re.compile(r"\brecursion|recursive\b", re.I)),
    ("oop", re.compile(
        r"\b(object[- ]oriented|oop|encapsulation|polymorphism|inheritance)\b", re.I
    )),
    ("networking", re.compile(r"\b(dns|http|https|tcp|ip address|networking)\b", re.I)),
    ("fees", re.compile(r"\b(fee|fees|tuition|payment|refund|late fee)\b", re.I)),
    ("hostel", re.compile(r"\b(hostel|mess|dorm)\b", re.I)),
    ("admissions", re.compile(r"\b(admission|eligibility|apply|application)\b", re.I)),
    ("library", re.compile(r"\b(library|borrow|fine)\b", re.I)),
    ("exams", re.compile(r"\b(exam|revaluation|hall ticket|malpractice)\b", re.I)),
]


def suggest_followups(
    *,
    question: str,
    intent: str | None = None,
    knowledge_mode: str | None = None,
    prior_context: str | None = None,
    max_items: int = 5,
) -> list[dict[str, Any]]:
    """
    Return 3–5 follow-up chips for the completed reply.

    Contract (stable for future LLM generators):
      [{"id": str, "label": str, "prompt": str, "source": "rules"}]
    """
    from backend.app.services.knowledge_mode_classifier import is_chitchat_query

    if is_chitchat_query(question or ""):
        topic = "greeting"
    else:
        blended = f"{prior_context or ''} {question or ''}".strip()
        topic = _detect_topic(blended, intent=intent, knowledge_mode=knowledge_mode)
    raw = list(_TOPIC_SUGGESTIONS.get(topic, _TOPIC_SUGGESTIONS["campus_general"]))
    limit = max(3, min(5, int(max_items)))
    selected = raw[:limit]
    return [
        {
            "id": f"fu-{topic}-{idx}",
            "label": item["label"],
            "prompt": item["prompt"],
            "source": "rules",
        }
        for idx, item in enumerate(selected)
    ]


def _detect_topic(
    question: str,
    *,
    intent: str | None,
    knowledge_mode: str | None,
) -> str:
    text = question.strip()
    for topic, pattern in _TOPIC_PATTERNS:
        if pattern.search(text):
            return topic
    if knowledge_mode == "general_ai" or intent == "out_of_scope":
        return "general_edu"
    return "campus_general"
