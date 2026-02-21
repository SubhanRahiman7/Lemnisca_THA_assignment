"""
Deterministic rule-based router: classify query as 'simple' or 'complex'.
Routes simple -> llama-3.1-8b-instant, complex -> llama-3.3-70b-versatile.
No LLM call; explicit signals only.
"""
import re
from dataclasses import dataclass
from typing import Literal

Classification = Literal["simple", "complex"]
MODEL_SIMPLE = "llama-3.1-8b-instant"
MODEL_COMPLEX = "llama-3.3-70b-versatile"

# Keywords that suggest a complex query (multi-step, reasoning, ambiguous)
COMPLEX_KEYWORDS = {
    "explain", "why", "how do i", "how can i", "how to", "compare", "difference",
    "difference between", "what's the difference", "troubleshoot", "fix", "error", "problem", "issue",
    "complaint", "not working", "doesn't work", "step by step", "walk me through",
    "multiple", "several", "both", "either", "depends", "ambiguous",
    "integrate", "integration", "api", "webhook", "configure", "configuration",
    "trying to understand", "set up", "set up permissions", "add team", "create a new project",
}
# Greeting/salutation patterns -> simple
SIMPLE_GREETINGS = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}


def _normalize(q: str) -> str:
    return " ".join(q.strip().lower().split())


def _word_count(q: str) -> int:
    return len(q.strip().split()) if q.strip() else 0


def _question_marks(q: str) -> int:
    return q.count("?")


def _has_complex_keyword(q_norm: str) -> bool:
    for kw in COMPLEX_KEYWORDS:
        if kw in q_norm:
            return True
    return False


def _is_greeting_only(q_norm: str, words: int) -> bool:
    if words > 4:
        return False
    return any(q_norm.startswith(g) or q_norm == g for g in SIMPLE_GREETINGS)


def classify(query: str) -> tuple[Classification, str]:
    """
    Rule-based classification. Returns (classification, model_used).
    Rules (evaluated in order):
    1. Empty or whitespace -> complex (safe default).
    2. Greeting-only (≤4 words, starts with hi/hello/etc.) -> simple.
    3. Contains any COMPLEX_KEYWORDS -> complex.
    4. More than one question mark -> complex.
    5. Word count ≥ 12 -> complex.
    6. Otherwise -> simple (short, single question, no complex keywords).
    """
    q_norm = _normalize(query)
    words = _word_count(q_norm)

    if not q_norm:
        return "complex", MODEL_COMPLEX

    if _is_greeting_only(q_norm, words):
        return "simple", MODEL_SIMPLE

    if _has_complex_keyword(q_norm):
        return "complex", MODEL_COMPLEX

    if _question_marks(query) >= 2:
        return "complex", MODEL_COMPLEX

    if words >= 12:
        return "complex", MODEL_COMPLEX

    return "simple", MODEL_SIMPLE


@dataclass
class RoutingLog:
    query: str
    classification: Classification
    model_used: str
    tokens_input: int
    tokens_output: int
    latency_ms: int
