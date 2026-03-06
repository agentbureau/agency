import sqlite3
import pytest
from agency.db.migrations import run_migrations, get_schema_version


@pytest.fixture
def migrated_db():
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    return conn


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


def test_schema_has_primitives_table(tmp_path):
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    for t in ["role_components", "desired_outcomes", "trade_off_configs",
              "agents", "templates", "pending_evaluations", "consumed_jwts",
              "seen_announcement_ids"]:
        assert t in tables, f"Missing table: {t}"


def test_projects_table_exists_after_migration(migrated_db):
    row = migrated_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
    ).fetchone()
    assert row is not None


def test_tasks_table_exists_after_migration(migrated_db):
    row = migrated_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
    ).fetchone()
    assert row is not None


def test_projects_table_has_admin_email_column(migrated_db):
    cols = [r[1] for r in migrated_db.execute("PRAGMA table_info(projects)").fetchall()]
    assert "admin_email" in cols


def test_tasks_table_has_agent_composition_id_column(migrated_db):
    cols = [r[1] for r in migrated_db.execute("PRAGMA table_info(tasks)").fetchall()]
    assert "agent_composition_id" in cols
