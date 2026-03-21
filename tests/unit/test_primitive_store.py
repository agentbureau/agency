import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive, get_primitive, find_similar
from agency.utils.errors import PrimitiveStoreEmpty
from agency.engine.assigner import assign_agent


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    return conn


@pytest.fixture
def empty_db():
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    return conn


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


def test_insert_and_retrieve(db):
    pid = insert_primitive(db, "role_components",
        description="evaluate task quality",
        instance_id="inst-1")
    p = get_primitive(db, "role_components", pid)
    assert p["description"] == "evaluate task quality"
    assert p["content_hash"]  # non-empty


def test_duplicate_content_hash_rejected(db):
    insert_primitive(db, "role_components",
        description="evaluate task quality", instance_id="i1")
    with pytest.raises(Exception):  # sqlite UNIQUE constraint
        insert_primitive(db, "role_components",
            description="evaluate task quality", instance_id="i1")


def test_find_similar_returns_results(db):
    insert_primitive(db, "role_components",
        description="evaluate task quality", instance_id="i1")
    insert_primitive(db, "role_components",
        description="assess performance of agents", instance_id="i1")
    results = find_similar(db, "role_components",
        query="measure how well tasks are done", limit=2)
    assert len(results) >= 1


def test_assign_agent_raises_when_store_empty(empty_db):
    with pytest.raises(PrimitiveStoreEmpty):
        assign_agent(empty_db, "task-1", {"task_description": "do a thing"})


def test_assign_agent_returns_embedding_vector(db_with_primitives):
    result = assign_agent(db_with_primitives, "t1", {"task_description": "write code"})
    assert "embedding_vector" in result
    assert isinstance(result["embedding_vector"], list)
    assert len(result["embedding_vector"]) > 0


def test_insert_primitive_accepts_scope_parameter(db):
    pid = insert_primitive(db, "role_components",
        description="meta: evaluate agent composition quality",
        instance_id="i1",
        scope="meta:assigner")
    p = get_primitive(db, "role_components", pid)
    assert p["scope"] == "meta:assigner"


def test_insert_primitive_defaults_to_task_scope(db):
    pid = insert_primitive(db, "role_components",
        description="write structured reports",
        instance_id="i1")
    p = get_primitive(db, "role_components", pid)
    assert p["scope"] == "task"


def test_insert_primitive_rejects_invalid_scope(db):
    with pytest.raises(ValueError, match="Invalid scope"):
        insert_primitive(db, "role_components",
            description="bad scope test",
            instance_id="i1",
            scope="invalid")
