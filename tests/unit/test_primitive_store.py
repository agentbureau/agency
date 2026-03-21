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


def test_insert_primitive_defaults_invalid_scope_to_task(db):
    pid = insert_primitive(db, "role_components",
        description="bad scope test",
        instance_id="i1",
        scope="invalid")
    row = db.execute("SELECT scope FROM role_components WHERE id = ?", (pid,)).fetchone()
    assert row[0] == "task"


def test_find_similar_returns_similarity_key(db):
    """Return dict uses 'similarity' not 'score'."""
    insert_primitive(db, "role_components",
        description="evaluate task quality", instance_id="i1")
    results = find_similar(db, "role_components", query="evaluate quality", limit=1)
    assert len(results) >= 1
    assert "similarity" in results[0]
    assert "score" not in results[0]


def test_find_similar_returns_name_field(db):
    """Return dict includes 'name' field."""
    insert_primitive(db, "role_components",
        description="evaluate task quality", instance_id="i1",
        name="Quality evaluator")
    results = find_similar(db, "role_components", query="evaluate quality", limit=1)
    assert results[0]["name"] == "Quality evaluator"


def test_find_similar_filters_by_scope(db):
    """Scope filter excludes primitives with different scope."""
    insert_primitive(db, "role_components",
        description="task-scoped role component for testing",
        instance_id="i1", scope="task")
    insert_primitive(db, "role_components",
        description="meta-scoped assigner role component",
        instance_id="i1", scope="meta:assigner")
    task_results = find_similar(db, "role_components",
        query="role component", limit=10, scope="task")
    meta_results = find_similar(db, "role_components",
        query="role component", limit=10, scope="meta:assigner")

    task_ids = {r["id"] for r in task_results}
    meta_ids = {r["id"] for r in meta_results}
    assert task_ids.isdisjoint(meta_ids)


def test_find_similar_scope_none_returns_all(db):
    """scope=None searches across all scopes."""
    insert_primitive(db, "role_components",
        description="task-scoped for none test",
        instance_id="i1", scope="task")
    insert_primitive(db, "role_components",
        description="meta-scoped for none test",
        instance_id="i1", scope="meta:assigner")
    all_results = find_similar(db, "role_components",
        query="none test", limit=10, scope=None)
    assert len(all_results) >= 2


def test_find_similar_default_scope_is_task(db):
    """Default scope='task' — existing callers get same behaviour."""
    insert_primitive(db, "role_components",
        description="default scope check item",
        instance_id="i1")
    insert_primitive(db, "role_components",
        description="meta scope check item",
        instance_id="i1", scope="meta:assigner")
    results = find_similar(db, "role_components",
        query="scope check item", limit=10)
    scopes_returned = set()
    for r in results:
        if "default scope" in r["description"]:
            scopes_returned.add("task")
        if "meta scope" in r["description"]:
            scopes_returned.add("meta")
    assert "task" in scopes_returned
    assert "meta" not in scopes_returned
