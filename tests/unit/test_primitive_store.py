import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive, get_primitive, find_similar


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
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
