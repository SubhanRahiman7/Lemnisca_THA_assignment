"""
Output evaluator: flag unreliable responses before showing to user.
Required: no_context, refusal, and one domain-specific check.
"""
import re
from typing import List

# Phrases that indicate refusal or "I don't know"
REFUSAL_PATTERNS = [
    r"i don'?t have",
    r"i do not have",
    r"not (?:mentioned|found|in the documentation|in the (?:provided )?context)",
    r"cannot (?:find|determine|answer|provide)",
    r"can'?t (?:find|determine|answer|provide)",
    r"no (?:relevant )?information (?:is )?(?:available|provided|found)",
    r"outside (?:my |the )?(?:knowledge|documentation)",
    r"not (?:enough )?information",
    r"unable to (?:find|answer|determine)",
    r"doesn'?t (?:say|mention|specify|appear)",
    r"don'?t (?:see|have) (?:any |the )?(?:information|details)",
    r"without (?:more |additional )?context",
    r"i (?:don'?t |do not )?know",
    r"i (?:am |'m )?not (?:sure|able)",
    r"cannot (?:be (?:determined|found)|find)",
]
REFUSAL_RE = re.compile("|".join(f"({p})" for p in REFUSAL_PATTERNS), re.I)

# Domain-specific: pricing uncertainty (conflicting or unclear pricing in answer)
# We flag if the answer mentions multiple different prices or "conflicting" / "varies"
PRICING_UNCERTAINTY_PATTERNS = [
    r"conflicting (?:information|pricing|prices)",
    r"(?:pricing|price|cost)(?:\s+)?(?:varies|differs|may vary)",
    r"\$\d+.*\$\d+",  # two different dollar amounts in same answer (could be different tiers)
    r"(?:one source says|another says|documentation (?:says|states))",
]
PRICING_UNCERTAINTY_RE = re.compile("|".join(f"({p})" for p in PRICING_UNCERTAINTY_PATTERNS), re.I)


def evaluate(
    answer: str,
    chunks_retrieved: int,
) -> List[str]:
    """
    Returns list of flag strings. Empty list if nothing to flag.
    Required flags: no_context, refusal, plus one custom (pricing_uncertainty).
    """
    flags: List[str] = []
    answer_lower = (answer or "").strip().lower()

    # 1. No-context: we answered but retrieved no chunks
    if chunks_retrieved == 0 and len(answer_lower) > 20:
        flags.append("no_context")

    # 2. Refusal / non-answer
    if REFUSAL_RE.search(answer or ""):
        flags.append("refusal")

    # 3. Domain-specific: pricing uncertainty (conflicting or unclear pricing)
    if PRICING_UNCERTAINTY_RE.search(answer or ""):
        flags.append("pricing_uncertainty")

    return flags
