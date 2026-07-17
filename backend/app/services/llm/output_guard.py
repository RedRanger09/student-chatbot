"""Detect and reject tool-/function-call shaped model output."""

from __future__ import annotations

import json
import re

# Models like Llama 3.1 sometimes emit fake tool calls instead of answers.
_TOOL_LIKE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE | re.DOTALL)
    for p in (
        r'^\s*\{?\s*"name"\s*:\s*"[^"]+"\s*,\s*"parameters"\s*:',
        r'^\s*\{\s*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:',
        r"<tool_call>",
        r"</tool_call>",
        r"<function_call>",
        r"\|?\s*tool\s*call\s*\|?",
        r"<\|python_tag\|>",
        r"^\s*call\s+\w+\s*\(",
        r"^\s*invoke\s+\w+\s*\(",
    )
)

ANTI_TOOL_CALL_INSTRUCTION = (
    "CRITICAL OUTPUT RULES:\n"
    "- Answer in natural language Markdown only.\n"
    "- Do NOT emit JSON tool calls, function calls, or action objects.\n"
    "- Do NOT output forms like "
    '{"name":"...","parameters":{...}} '
    "or <tool_call>...</tool_call>.\n"
    "- If the student asked for a summary or bullets, write the bullets directly."
)


def looks_like_tool_call(text: str | None) -> bool:
    """True when the model output looks like a tool/function invocation."""
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    # Trailing junk like "?" after JSON still counts.
    probe = cleaned.rstrip("?!. \n\t")
    for pattern in _TOOL_LIKE_PATTERNS:
        if pattern.search(probe):
            return True
    if probe.startswith("{") and '"name"' in probe and (
        '"parameters"' in probe or '"arguments"' in probe
    ):
        try:
            data = json.loads(probe)
        except json.JSONDecodeError:
            # Often almost-JSON with a trailing character — still treat as tool noise.
            return '"parameters"' in probe or '"arguments"' in probe
        if isinstance(data, dict) and "name" in data and (
            "parameters" in data or "arguments" in data
        ):
            return True
    return False


def message_has_tool_calls(message: dict | None) -> bool:
    """True when an OpenAI-style message object includes tool_calls."""
    if not isinstance(message, dict):
        return False
    if message.get("tool_calls"):
        return True
    if message.get("function_call"):
        return True
    return False
