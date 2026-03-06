import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.projects import create_project, get_project


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    return conn


def test_create_and_get_project(db):
    pid = create_project(db, name="test", client_id=None, description=None, admin_email="admin@example.com")
    project = get_project(db, pid)
    assert project["name"] == "test"
    assert project["admin_email"] == "admin@example.com"


def test_get_project_returns_none_if_missing(db):
    assert get_project(db, "nonexistent") is None
