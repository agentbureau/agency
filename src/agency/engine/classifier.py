"""Task-type keyword classifier for pre-classification gate (v1.2.4 Issue 8).

Classifies task descriptions into types before embedding search.
Keyword-based — no LLM call required.
"""

from agency.engine.constants import TASK_TYPE_KEYWORDS, TASK_TYPE_DEFAULT


def classify_task_type(description: str) -> str:
    """Classify a task description into a task type by keyword matching.

    Returns one of: "research", "build", "review", "analyse", "write",
    "design", "debug", "plan", "audit", "evaluate", "advise", "synthesise".
    Falls back to "analyse" if no keywords match.
    """
    desc_lower = description.lower()
    scores: dict[str, int] = {}
    for task_type, keywords in TASK_TYPE_KEYWORDS.items():
        scores[task_type] = sum(1 for kw in keywords if kw in desc_lower)
    if max(scores.values()) == 0:
        return TASK_TYPE_DEFAULT
    # On tie, the type listed first in TASK_TYPE_KEYWORDS wins (dict insertion order).
    return max(scores, key=scores.get)


def estimate_method_absence(description: str) -> float:
    """Estimate how much analytical method is absent from the prompt.

    Returns 0.0–1.0. Higher = more method-absent = more room for
    Agency to add value.
    """
    from agency.engine.constants import METHOD_INDICATOR_VERBS

    desc_lower = description.lower()
    hits = sum(1 for verb in METHOD_INDICATOR_VERBS if verb in desc_lower)
    if hits == 0:
        return 1.0
    elif hits == 1:
        return 0.7
    elif hits == 2:
        return 0.4
    else:
        return 0.0
