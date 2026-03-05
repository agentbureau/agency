import sqlite3
import pytest
from unittest.mock import AsyncMock, MagicMock
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive
from agency.db.compositions import upsert_agent
from agency.engine.evolver import random_perturbation, llm_variation, select_best_variant


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    # Insert several similar role components so perturbation has candidates
    for desc in [
        "evaluate task quality and completeness",
        "assess output quality against criteria",
        "review task for accuracy and clarity",
        "score output on predefined rubric",
    ]:
        insert_primitive(conn, "role_components", description=desc, instance_id="inst-1")
    insert_primitive(conn, "desired_outcomes",
                     description="produce quality assessment", instance_id="inst-1")
    return conn


@pytest.fixture
def agent_id(db):
    rows = db.execute("SELECT id FROM role_components LIMIT 2").fetchall()
    role_ids = [r[0] for r in rows]
    outcome = db.execute("SELECT id FROM desired_outcomes LIMIT 1").fetchone()
    return upsert_agent(db, role_component_ids=role_ids,
                        desired_outcome_id=outcome[0] if outcome else None,
                        trade_off_config_id=None, instance_id="inst-1")


# Task 25
def test_random_perturbation_returns_n_variants(db, agent_id):
    variants = random_perturbation(db, agent_id, "inst-1", n_variants=3)
    assert len(variants) == 3


def test_random_perturbation_variants_are_agent_ids(db, agent_id):
    variants = random_perturbation(db, agent_id, "inst-1", n_variants=2)
    for v in variants:
        assert isinstance(v, str)
        assert len(v) > 0


def test_random_perturbation_unknown_agent_returns_original(db):
    variants = random_perturbation(db, "nonexistent-id", "inst-1", n_variants=2)
    assert variants == ["nonexistent-id", "nonexistent-id"]


# Task 26
@pytest.mark.asyncio
async def test_llm_variation_uses_mock(db, agent_id):
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="critically evaluate task output for completeness")
    variant_id = await llm_variation(db, agent_id, "grade this essay", "inst-1", llm)
    assert variant_id
    llm.complete.assert_called_once()


@pytest.mark.asyncio
async def test_llm_variation_deduplicates_existing(db, agent_id):
    # Return a description that closely matches an existing component
    llm = MagicMock()
    existing_desc = db.execute(
        "SELECT description FROM role_components LIMIT 1"
    ).fetchone()[0]
    llm.complete = AsyncMock(return_value=existing_desc)
    variant_id = await llm_variation(db, agent_id, "grade this essay", "inst-1", llm)
    assert variant_id  # should succeed without duplicate insert error


# Task 27
def test_select_best_variant_returns_highest_score():
    variants = [("agent-a", 0.72), ("agent-b", 0.91), ("agent-c", 0.65)]
    assert select_best_variant(variants) == "agent-b"


def test_select_best_variant_single_entry():
    assert select_best_variant([("agent-x", 0.5)]) == "agent-x"


def test_select_best_variant_empty_raises():
    with pytest.raises(ValueError):
        select_best_variant([])
