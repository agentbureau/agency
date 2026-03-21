import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive
from agency.engine.assigner import assign_agents_batch, deduplicate_compositions
from agency.models.tasks import BatchTaskRequest


@pytest.fixture
def db_with_primitives():
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    insert_primitive(conn, "role_components",
                     description="write clear and concise code",
                     instance_id="inst-1")
    insert_primitive(conn, "desired_outcomes",
                     description="produce working, tested code",
                     instance_id="inst-1")
    insert_primitive(conn, "trade_off_configs",
                     description="quality over speed",
                     instance_id="inst-1")
    return conn


def test_deduplicate_identical_compositions():
    comps = [
        type("C", (), {"embedding": [1.0, 0.0]})(),
        type("C", (), {"embedding": [1.0, 0.0]})(),
        type("C", (), {"embedding": [0.0, 1.0]})(),
    ]
    clusters = deduplicate_compositions(comps, threshold=0.90)
    assert len(clusters) == 2
    assert len(clusters[0]) == 2  # first two are identical
    assert len(clusters[1]) == 1


def test_assign_agents_batch_returns_packet(db_with_primitives):
    tasks = [
        BatchTaskRequest(external_id="t1", description="write tests"),
        BatchTaskRequest(external_id="t2", description="write more tests"),
    ]
    packet = assign_agents_batch(tasks, db_with_primitives, {})
    assert "t1" in packet["assignments"]
    assert "t2" in packet["assignments"]
    assert len(packet["agents"]) >= 1

    # v1.2.3: verify agent_id propagation
    for ext_id in ("t1", "t2"):
        assert "agent_id" in packet["assignments"][ext_id]

    for agent_hash, agent_def in packet["agents"].items():
        assert "agent_id" in agent_def
        assert "composition_fitness" in agent_def


def test_batch_response_includes_agent_id(db_with_primitives):
    """Bug 17a: agent_id (UUID) must be in both assignments and agents dicts."""
    tasks = [
        BatchTaskRequest(external_id="t1", description="write tests"),
    ]
    packet = assign_agents_batch(tasks, db_with_primitives, {})

    # Each assignment must have agent_id
    assignment = packet["assignments"]["t1"]
    assert "agent_id" in assignment
    agent_id = assignment["agent_id"]

    # agent_id must be a UUID (36 chars), not a SHA-256 (64 chars)
    assert len(agent_id) == 36, f"agent_id should be UUID (36 chars), got {len(agent_id)} chars"

    # agents dict must also have agent_id
    agent_hash = assignment["agent_hash"]
    assert "agent_id" in packet["agents"][agent_hash]
    assert packet["agents"][agent_hash]["agent_id"] == agent_id

    # agent_id must exist in the agents table
    row = db_with_primitives.execute(
        "SELECT id FROM agents WHERE id = ?", (agent_id,)
    ).fetchone()
    assert row is not None, f"agent_id {agent_id} not found in agents table"


def test_batch_dedup_shares_canonical_agent_id(db_with_primitives):
    """Bug 17a: deduplicated tasks share the canonical agent's UUID."""
    tasks = [
        BatchTaskRequest(external_id="t1", description="write tests"),
        BatchTaskRequest(external_id="t2", description="write tests"),  # identical
    ]
    packet = assign_agents_batch(tasks, db_with_primitives, {})
    id1 = packet["assignments"]["t1"]["agent_id"]
    id2 = packet["assignments"]["t2"]["agent_id"]
    assert len(id1) == 36
    assert len(id2) == 36
