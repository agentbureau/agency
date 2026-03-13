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


def test_issued_tokens_table_exists(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='issued_tokens'")
    assert cursor.fetchone() is not None


def test_pending_evaluations_table_exists(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_evaluations'")
    assert cursor.fetchone() is not None


def test_primitive_mutations_table_exists(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='primitive_mutations'")
    assert cursor.fetchone() is not None


def test_primitives_view_exists(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='primitives'")
    assert cursor.fetchone() is not None


def test_role_components_has_quality_and_permission_block(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cursor = conn.execute("PRAGMA table_info(role_components)")
    cols = {row[1] for row in cursor.fetchall()}
    assert "quality" in cols
    assert "permission_block" in cols
    assert "override_capability" in cols
    assert "name" in cols
    assert "domain_specificity" in cols
    assert "domain" in cols
    assert "origin_instance_id" in cols
    assert "parent_content_hash" in cols


def test_desired_outcomes_has_quality_no_override_capability(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cursor = conn.execute("PRAGMA table_info(desired_outcomes)")
    cols = {row[1] for row in cursor.fetchall()}
    assert "quality" in cols
    assert "permission_block" in cols
    assert "override_capability" not in cols


def test_agents_has_permission_block(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cursor = conn.execute("PRAGMA table_info(agents)")
    cols = {row[1] for row in cursor.fetchall()}
    assert "permission_block" in cols


def test_projects_has_all_new_columns(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cursor = conn.execute("PRAGMA table_info(projects)")
    cols = {row[1] for row in cursor.fetchall()}
    expected = {"name", "contact_email", "oversight_preference", "error_notification_timeout",
                "llm_provider", "llm_model", "llm_api_key", "homepool_retry_max_interval",
                "permission_block", "attribution"}
    assert expected.issubset(cols)
