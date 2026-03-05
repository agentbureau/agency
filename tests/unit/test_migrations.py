import sqlite3
import pytest
from agency.db.migrations import run_migrations, get_schema_version


def test_fresh_db_starts_at_version_zero(tmp_path):
    db_path = tmp_path / "agency.db"
    conn = sqlite3.connect(db_path)
    assert get_schema_version(conn) == 0


def test_migrations_advance_schema_version(tmp_path):
    db_path = tmp_path / "agency.db"
    conn = sqlite3.connect(db_path)
    run_migrations(conn)
    assert get_schema_version(conn) >= 1


def test_migrations_are_idempotent(tmp_path):
    db_path = tmp_path / "agency.db"
    conn = sqlite3.connect(db_path)
    run_migrations(conn)
    v1 = get_schema_version(conn)
    run_migrations(conn)
    v2 = get_schema_version(conn)
    assert v1 == v2
