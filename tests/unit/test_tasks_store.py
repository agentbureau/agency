import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.tasks import create_task, get_task, set_task_composition


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    return conn


def test_create_and_get_task(db):
    tid = create_task(db, description="do the thing")
    task = get_task(db, tid)
    assert task["description"] == "do the thing"
    assert task["agent_composition_id"] is None


def test_get_task_returns_none_if_missing(db):
    assert get_task(db, "nonexistent") is None


def test_set_task_composition(db):
    tid = create_task(db, description="do the thing")
    set_task_composition(db, tid, "comp-abc")
    task = get_task(db, tid)
    assert task["agent_composition_id"] == "comp-abc"
