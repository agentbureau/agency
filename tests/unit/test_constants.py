"""Test that all v1.2.3 assigner/triage constants are importable and have correct values."""


def test_metaprimitive_similarity_threshold():
    from agency.engine.constants import METAPRIMITIVE_SIMILARITY_THRESHOLD
    assert METAPRIMITIVE_SIMILARITY_THRESHOLD == 0.35


def test_pool_coverage_warning_threshold():
    from agency.engine.constants import POOL_COVERAGE_WARNING_THRESHOLD
    assert POOL_COVERAGE_WARNING_THRESHOLD == 0.45


def test_find_similar_similarity_key():
    from agency.engine.constants import FIND_SIMILAR_SIMILARITY_KEY
    assert FIND_SIMILAR_SIMILARITY_KEY == "similarity"


def test_assigner_strategy_constants():
    from agency.engine.constants import (
        ASSIGNER_STRATEGY_KEY,
        ASSIGNER_STRATEGY_EMBEDDING,
        ASSIGNER_STRATEGY_LLM,
    )
    assert ASSIGNER_STRATEGY_KEY == "strategy"
    assert ASSIGNER_STRATEGY_EMBEDDING == "embedding"
    assert ASSIGNER_STRATEGY_LLM == "llm"


def test_triage_top_n():
    from agency.engine.constants import TRIAGE_TOP_N
    assert TRIAGE_TOP_N == 5


def test_assigner_llm_constants():
    from agency.engine.constants import (
        ASSIGNER_LLM_MODEL,
        ASSIGNER_LLM_TIMEOUT,
        ASSIGNER_LLM_MAX_RETRIES,
    )
    assert ASSIGNER_LLM_MODEL == "claude-haiku-4-5-20251001"
    assert ASSIGNER_LLM_TIMEOUT == 30
    assert ASSIGNER_LLM_MAX_RETRIES == 1


def test_skill_tag_boost_factor():
    from agency.engine.constants import SKILL_TAG_BOOST_FACTOR
    assert SKILL_TAG_BOOST_FACTOR == 1.3


def test_assigner_fallback_log():
    from agency.engine.constants import ASSIGNER_FALLBACK_LOG
    assert ASSIGNER_FALLBACK_LOG == "~/.agency/assigner-fallback.log"


def test_llm_assigner_available_flag():
    from agency.engine.constants import LLM_ASSIGNER_AVAILABLE_FLAG
    assert LLM_ASSIGNER_AVAILABLE_FLAG == "llm_assigner_available"
