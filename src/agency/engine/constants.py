"""v1.2.3 assigner and triage constants.

Central registry for all constants used by the dual-path assigner (§4.4),
relevance floor (§4.4.2a), skill tag boost (§4.4.2b), fitness metadata
(§4.4.2c), and the triage endpoint (§4.7.5). Imported by Tracks C1, C2,
and G without cross-track dependencies.
"""

# --- Similarity thresholds ---

# Relevance floor: primitives below this cosine similarity are excluded
# from composition slots (§4.4.2a).
METAPRIMITIVE_SIMILARITY_THRESHOLD: float = 0.35

# Pool coverage warning: if no primitive in any slot exceeds this,
# composition_fitness.pool_coverage_warning is True (§4.4.2c).
POOL_COVERAGE_WARNING_THRESHOLD: float = 0.45

# Return key name for cosine similarity in find_similar() results.
FIND_SIMILAR_SIMILARITY_KEY: str = "similarity"

# --- Assigner strategy (feature flag, §4.4.1) ---

# Key in agency.toml [assigner] section.
ASSIGNER_STRATEGY_KEY: str = "strategy"

# Strategy values.
ASSIGNER_STRATEGY_EMBEDDING: str = "embedding"
ASSIGNER_STRATEGY_LLM: str = "llm"

# --- Triage (§4.7.5) ---

# Per-slot top_n argument to find_similar() and post-merge truncation
# limit in POST /triage.
TRIAGE_TOP_N: int = 5

# --- LLM path defaults (§4.4.3) ---

ASSIGNER_LLM_MODEL: str = "claude-haiku-4-5-20251001"
ASSIGNER_LLM_TIMEOUT: int = 30  # seconds before fallback to embedding path
ASSIGNER_LLM_MAX_RETRIES: int = 1  # retries on parse failure before fallback

# --- Skill tag boost (§4.4.2b) ---

# Multiplier for primitives whose description matches a skill tag.
# Post-multiply value is capped at 1.0.
SKILL_TAG_BOOST_FACTOR: float = 1.3

# --- Fallback telemetry (§4.4.3c) ---

ASSIGNER_FALLBACK_LOG: str = "~/.agency/assigner-fallback.log"

# --- Feature activation (status file, §4.4.1) ---

# Key in agency-status.json that signals LLM path is available.
LLM_ASSIGNER_AVAILABLE_FLAG: str = "llm_assigner_available"

# --- Composition fitness floor (v1.2.4 Issue 4) ---

# Below this, composition is actively unhelpful across all rounds and models.
# Calibration: round 7 all 7 races at 0.415–0.453, Agency 5-0-2.
# Rounds 1–6 confirm: below 0.39, Agency wins 0 races.
COMPOSITION_FITNESS_FLOOR: float = 0.39

# Upper fitness band boundary. Above this, Agency is favoured.
COMPOSITION_FITNESS_GOOD_THRESHOLD: float = 0.50

# --- Task-type pre-classification (v1.2.4 Issue 8) ---

TASK_TYPE_KEYWORDS: dict[str, list[str]] = {
    "synthesise": ["synthesise", "synthesize", "bring together", "consolidate",
                   "unify", "reconcile findings", "cross-cutting", "integrate the",
                   "combine the"],
    "review": ["review", "check this", "inspect", "examine", "look at",
               "go through", "assess this", "feedback on", "review the"],
    "audit": ["audit", "verify", "validate", "compliance",
              "check against", "does this meet", "for pii", "exposure"],
    "advise": ["advise", "recommend", "suggest", "what should", "counsel",
               "guidance", "strategic", "what would you", "pricing strategy"],
    "research": ["research", "investigate", "find out", "literature", "survey",
                 "cite", "sources", "bibliography", "what does the evidence"],
    "build": ["build", "create a", "implement", "develop", "code", "deploy",
              "ship", "construct", "set up", "install"],
    "analyse": ["analyse", "analyze", "break down", "decompose", "compare",
                "contrast", "identify patterns", "what explains"],
    "write": ["write", "draft", "compose", "author", "produce a document",
              "blog post", "essay", "memo", "newsletter"],
    "design": ["design", "architect", "lay out", "propose a model",
               "propose a data model", "framework for", "three-tier"],
    "debug": ["debug", "troubleshoot", "diagnose", "why is this",
              "failing", "broken", "returns 502", "returns 500"],
    "plan": ["plan", "roadmap", "schedule", "sequence", "prioritise",
             "what order", "timeline", "milestones"],
    "evaluate": ["evaluate", "score", "rate", "rank", "judge", "assess quality",
                 "how good", "which is better"],
}

TASK_TYPE_DEFAULT: str = "analyse"

# Agency probability by task type (Horse Race rounds 1–9, 58 races).
AGENCY_PROBABILITY_BY_TYPE: dict[str, str] = {
    "review": "high", "audit": "high", "advise": "high",
    "analyse": "moderate", "evaluate": "moderate", "synthesise": "moderate",
    "design": "neutral", "build": "neutral", "plan": "neutral", "debug": "neutral",
    "write": "low", "research": "low",
}

# Analytical method indicator verbs — presence suggests prompt already prescribes the approach.
METHOD_INDICATOR_VERBS: list[str] = [
    "distinguish", "differentiate", "classify according to",
    "evaluate by", "assess against", "compare using",
    "identify the assumption", "test whether", "generate the strongest",
    "apply the framework", "use the criteria", "score against",
    "rank by", "prioritise according to",
]

# Method absence estimation thresholds (Issue 17).
METHOD_ABSENCE_HIGH: float = 0.7
METHOD_ABSENCE_MODERATE: float = 0.4
