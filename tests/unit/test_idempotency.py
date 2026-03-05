import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.idempotency import record_jwt, is_duplicate


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    return conn


def test_first_jwt_not_duplicate(db):
    assert not is_duplicate(db, "jwt-1", "task-1")


def test_recorded_jwt_is_duplicate(db):
    record_jwt(db, "jwt-1", "task-1")
    assert is_duplicate(db, "jwt-1", "task-1")


def test_same_jwt_different_task_not_duplicate(db):
    record_jwt(db, "jwt-1", "task-1")
    assert not is_duplicate(db, "jwt-1", "task-2")
