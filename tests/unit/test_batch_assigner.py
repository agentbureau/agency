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
