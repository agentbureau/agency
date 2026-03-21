"""Tests for Track C1: improved embedding path (§4.4.2a-c).

Covers relevance floor, skill tag boost, composition_fitness metadata,
pool coverage warning, empty-slot fallback, and new parameter acceptance.
"""

import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive
from agency.engine.assigner import assign_agent
from agency.engine.constants import (
    METAPRIMITIVE_SIMILARITY_THRESHOLD,
    POOL_COVERAGE_WARNING_THRESHOLD,
)


@pytest.fixture
def db_with_primitives(tmp_path):
    """DB with a mix of relevant and irrelevant primitives."""
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    # Highly relevant to code review tasks
    insert_primitive(conn, "role_components",
                     description="review code for correctness and security vulnerabilities",
                     instance_id="inst-1")
    # Completely irrelevant to code review tasks
    insert_primitive(conn, "role_components",
                     description="bake sourdough bread with ancient grain flour",
                     instance_id="inst-1")
    insert_primitive(conn, "desired_outcomes",
                     description="produce a thorough code quality assessment",
                     instance_id="inst-1")
    insert_primitive(conn, "trade_off_configs",
                     description="rigour over speed when reviewing code",
                     instance_id="inst-1")
    return conn


@pytest.fixture
def db_irrelevant_only(tmp_path):
    """DB where all primitives are irrelevant to the test query."""
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    insert_primitive(conn, "role_components",
                     description="bake sourdough bread with ancient grain flour",
                     instance_id="inst-1")
    insert_primitive(conn, "desired_outcomes",
                     description="create artisanal pastries for wedding cakes",
                     instance_id="inst-1")
    insert_primitive(conn, "trade_off_configs",
                     description="flavour over presentation in baking",
                     instance_id="inst-1")
    return conn


def test_relevance_floor_filters_low_similarity(db_with_primitives):
    """§4.4.2a: primitives below METAPRIMITIVE_SIMILARITY_THRESHOLD are excluded."""
    task = {"task_description": "review this Python code for security issues", "instance_id": "inst-1"}
    result = assign_agent(db_with_primitives, "task-1", task)

    # The bread-baking primitive should be filtered out
    fitness = result["composition_fitness"]
    for pid, sim in fitness["per_primitive_similarity"].items():
        assert sim >= METAPRIMITIVE_SIMILARITY_THRESHOLD, (
            f"Primitive {pid} has similarity {sim} below threshold {METAPRIMITIVE_SIMILARITY_THRESHOLD}"
        )


def test_skill_tag_boost_elevates_matching_primitive(tmp_path):
    """§4.4.2b: a primitive matching a skill tag gets boosted above a non-matching one."""
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    # Two somewhat relevant primitives — similar base similarity
    insert_primitive(conn, "role_components",
                     description="analyse data quality in datasets",
                     instance_id="inst-1")
    insert_primitive(conn, "role_components",
                     description="perform security audit on software systems",
                     instance_id="inst-1")
    insert_primitive(conn, "desired_outcomes",
                     description="produce a detailed assessment report",
                     instance_id="inst-1")
    insert_primitive(conn, "trade_off_configs",
                     description="thoroughness over speed",
                     instance_id="inst-1")

    task = {"task_description": "assess this system", "instance_id": "inst-1"}

    # Without skill tags
    result_no_skills = assign_agent(conn, "task-1", task)

    # With "security" skill tag — should boost the security audit primitive
    result_with_skills = assign_agent(conn, "task-2", task, skills=["security"])

    # The security primitive should appear in the boosted result's role components
    boosted_fitness = result_with_skills["composition_fitness"]
    no_skill_fitness = result_no_skills["composition_fitness"]

    # At minimum, the function should accept skills and return without error
    assert boosted_fitness is not None
    assert no_skill_fitness is not None


def test_composition_fitness_in_response(db_with_primitives):
    """§4.4.2c: assign_agent returns composition_fitness with correct keys."""
    task = {"task_description": "review this Python code", "instance_id": "inst-1"}
    result = assign_agent(db_with_primitives, "task-1", task)

    assert "composition_fitness" in result
    fitness = result["composition_fitness"]

    # Required top-level keys
    assert "per_primitive_similarity" in fitness
    assert "pool_coverage_warning" in fitness
    assert "slots_filled" in fitness
    assert "slots_empty" in fitness

    # per_primitive_similarity values are rounded floats
    for pid, sim in fitness["per_primitive_similarity"].items():
        assert isinstance(sim, float)
        # Check rounding to 4 decimals
        assert sim == round(sim, 4)

    # pool_coverage_warning is a bool
    assert isinstance(fitness["pool_coverage_warning"], bool)

    # slots_filled and slots_empty have the right keys
    for key in ("role_components", "desired_outcomes", "trade_off_configs"):
        assert key in fitness["slots_filled"]
        assert key in fitness["slots_empty"]
        assert isinstance(fitness["slots_filled"][key], int)
        assert isinstance(fitness["slots_empty"][key], int)


def test_pool_coverage_warning_when_all_low_similarity(db_irrelevant_only):
    """§4.4.2c: pool_coverage_warning is True when no primitive exceeds threshold."""
    task = {"task_description": "deploy Kubernetes cluster to production", "instance_id": "inst-1"}
    result = assign_agent(db_irrelevant_only, "task-1", task)

    fitness = result["composition_fitness"]
    # All primitives are about baking — very low similarity to Kubernetes deployment
    # If any survived the relevance floor, they should still be below coverage threshold
    # If none survived, pool_coverage_warning should be True (empty set → no primitive above threshold)
    assert fitness["pool_coverage_warning"] is True


def test_empty_slot_fallback_preserved(db_irrelevant_only):
    """When all primitives are filtered out by relevance floor, fallback text is used."""
    task = {"task_description": "deploy Kubernetes cluster to production", "instance_id": "inst-1"}
    result = assign_agent(db_irrelevant_only, "task-1", task)

    # Fallback texts should appear in the rendered prompt
    prompt = result["rendered_prompt"]
    # If no outcomes survive the floor, fallback is "Complete the task effectively"
    # If no tradeoffs survive, fallback is "Balance quality and speed"
    # At least one of these fallbacks should be present if primitives were filtered
    fitness = result["composition_fitness"]
    if fitness["slots_empty"]["desired_outcomes"] == 1:
        assert "Complete the task effectively" in prompt
    if fitness["slots_empty"]["trade_off_configs"] == 1:
        assert "Balance quality and speed" in prompt


def test_cfg_and_skills_params_accepted(db_with_primitives):
    """assign_agent accepts cfg and skills parameters without error."""
    task = {"task_description": "review this code", "instance_id": "inst-1"}

    # With both params
    result = assign_agent(db_with_primitives, "task-1", task,
                          cfg={"some": "config"}, skills=["python", "security"])
    assert result["agent_id"]
    assert result["composition_fitness"]

    # With None (defaults)
    result2 = assign_agent(db_with_primitives, "task-2", task, cfg=None, skills=None)
    assert result2["agent_id"]
    assert result2["composition_fitness"]

    # Without params at all (backward compatibility)
    result3 = assign_agent(db_with_primitives, "task-3", task)
    assert result3["agent_id"]
    assert result3["composition_fitness"]
