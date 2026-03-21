"""v1.2.3 assigner and triage constants.

Central registry for all constants used by the dual-path assigner (§4.4),
relevance floor (§4.4.2a), skill tag boost (§4.4.2b), fitness metadata
(§4.4.2c), and the triage endpoint (§4.7.5). Imported by Tracks C1, C2,
and G without cross-track dependencies.
"""

# --- Similarity thresholds ---

# Relevance floor: primitives below this cosine similarity are excluded
# from composition slots (§4.4.2a).
METAPRIMITIVE_SIMILARITY_THRESHOLD: float = 0.5

# Pool coverage warning: if no primitive in any slot exceeds this,
# composition_fitness.pool_coverage_warning is True (§4.4.2c).
POOL_COVERAGE_WARNING_THRESHOLD: float = 0.6

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
