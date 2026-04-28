"""
response_cleaner.py
-------------------
Post-processing layer that strips internal system markers from
the model's final user-facing response.

Why this exists (defense in depth):
  Even with good system prompt rules and clean tool descriptions,
  the model sometimes leaks internal markers into responses.
  Examples of leaks we've seen:
    - "[PRIVATE] Results for..." appears in response text
    - Model says "the private_search function is locked"
    - Model says "not available in current session"

  This cleaner is the last line of defense — it catches what
  prompt engineering misses.

  Lesson: Never rely on a single protection layer.
          Stack independent layers. Each catches what the others miss.
"""

import re

# ── Patterns to strip from model responses ────────────────────────────────────
# Each pattern targets a specific class of internal leak observed in testing

UX_LEAK_PATTERNS = [
    r"\[PUBLIC\]",                                      # tool result prefix
    r"\[PRIVATE\]",                                     # tool result prefix
    r"\[ADVANCED\]",                                    # tool result prefix
    r"__ACCESS_DENIED__",                               # guarded function return
    r"(?i)tool(s)?\s+(is|are)\s+(locked|unavailable)", # "tool is locked"
    r"(?i)not available in (the )?current session",     # session language
    r"(?i)(public|private|advanced)_search\s+(is|function)", # tool name leaks
]

# ── Phrases that should never appear in user-facing responses ─────────────────
UX_VIOLATION_PHRASES = [
    "locked",
    "not available",
    "cannot provide",
    "private_search",
    "public_search",
    "advanced_search",
    "function is",
    "tool is",
    "current session",
    "__ACCESS_DENIED__",
    "[PUBLIC]",
    "[PRIVATE]",
    "[ADVANCED]",
]


def clean_response(text: str) -> str:
    """
    Strip internal system markers from model response text.

    Applies regex patterns to remove any leaked tool markers,
    access-denied strings, or internal system language.

    Args:
        text: Raw response text from the model

    Returns:
        Cleaned text safe to show to users
    """
    cleaned = text
    for pattern in UX_LEAK_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    return cleaned.strip()


def check_ux_quality(text: str) -> tuple:
    """
    Check whether a response contains any internal system language.

    Used by the evaluator to measure UX Quality as a separate metric
    from tool routing accuracy.

    Args:
        text: Cleaned response text to inspect

    Returns:
        Tuple of (is_clean: bool, violations: list[str])
        is_clean is True when no violation phrases found
    """
    violations = [
        phrase for phrase in UX_VIOLATION_PHRASES
        if phrase.lower() in text.lower()
    ]
    return len(violations) == 0, violations
