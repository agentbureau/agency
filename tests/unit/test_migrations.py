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


def test_agents_has_template_id_column(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cursor = conn.execute("PRAGMA table_info(agents)")
    col_info = {row[1]: row for row in cursor.fetchall()}
    assert "template_id" in col_info
    # Check default value is 'default'
    dflt = col_info["template_id"][4]  # dflt_value is index 4
    assert dflt == "'default'"


def test_template_id_migration_preserves_existing_agents(tmp_path):
    """Existing agents should get template_id='default' after migration."""
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    # Insert an agent row
    conn.execute(
        """INSERT INTO agents (id, role_component_ids, content_hash, instance_id)
           VALUES ('agent-1', '["rc-1"]', 'hash-1', 'inst-1')"""
    )
    conn.commit()
    row = conn.execute("SELECT template_id FROM agents WHERE id = 'agent-1'").fetchone()
    assert row[0] == "default"


def test_projects_has_all_new_columns(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cursor = conn.execute("PRAGMA table_info(projects)")
    cols = {row[1] for row in cursor.fetchall()}
    expected = {"name", "contact_email", "oversight_preference", "error_notification_timeout",
                "llm_provider", "llm_model", "llm_api_key", "homepool_retry_max_interval",
                "permission_block", "attribution"}
    assert expected.issubset(cols)


def test_migration_fixes_agent_composition_id_sha256_to_uuid():
    """Bug 17a data migration: SHA-256 content_hash → UUID agent_id."""
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)

    # Simulate the bug state: agent exists, task has SHA-256 instead of UUID
    sha256_hash = "a" * 64
    conn.execute(
        """INSERT INTO agents (id, role_component_ids, content_hash, instance_id, template_id)
           VALUES (?, '["r1"]', ?, 'inst-1', 'default')""",
        ("019d-uuid-agent", sha256_hash),
    )
    conn.execute(
        """INSERT INTO tasks (id, description, agent_composition_id)
           VALUES ('task-1', 'test', ?)""",
        (sha256_hash,),
    )
    conn.commit()

    # Call the migration function directly (run_migrations already ran it on empty data)
    from agency.db.schema import fix_v123_persistence_bugs
    fix_v123_persistence_bugs(conn)
    conn.commit()

    row = conn.execute(
        "SELECT agent_composition_id FROM tasks WHERE id = 'task-1'"
    ).fetchone()
    assert row[0] == "019d-uuid-agent", f"Expected UUID, got {row[0]}"


def test_migration_confirms_existing_instance_evaluations():
    """Bug 17b data migration: confirm all agency_instance evaluations."""
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)

    # Insert unconfirmed instance evaluation (the bug state)
    conn.execute(
        """INSERT INTO pending_evaluations
           (id, task_id, evaluator_data, destination, content_hash, confirmed)
           VALUES ('eval-1', 'task-1', '{}', 'agency_instance', 'hash1', 0)"""
    )
    conn.commit()

    # Call the migration function directly
    from agency.db.schema import fix_v123_persistence_bugs
    fix_v123_persistence_bugs(conn)
    conn.commit()

    row = conn.execute(
        "SELECT confirmed, confirmed_at FROM pending_evaluations WHERE id = 'eval-1'"
    ).fetchone()
    assert row[0] == 1, "evaluation should be confirmed after migration"
    assert row[1] is not None, "confirmed_at should be set"


def test_scope_column_exists_on_role_components(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(role_components)").fetchall()}
    assert "scope" in cols


def test_scope_column_exists_on_desired_outcomes(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(desired_outcomes)").fetchall()}
    assert "scope" in cols


def test_scope_column_exists_on_trade_off_configs(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(trade_off_configs)").fetchall()}
    assert "scope" in cols


def test_scope_column_defaults_to_task(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    conn.execute(
        """INSERT INTO role_components
           (id, name, description, content_hash, instance_id, embedding)
           VALUES ('rc-scope-1', 'test', 'test desc', 'hash-scope-1', 'inst-1', '[]')"""
    )
    conn.commit()
    row = conn.execute("SELECT scope FROM role_components WHERE id = 'rc-scope-1'").fetchone()
    assert row[0] == "task"


def test_primitives_view_includes_scope(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)
    conn.execute(
        """INSERT INTO role_components
           (id, name, description, content_hash, instance_id, embedding)
           VALUES ('rc-scope-2', 'test', 'test desc', 'hash-scope-2', 'inst-1', '[]')"""
    )
    conn.commit()
    row = conn.execute("SELECT scope FROM primitives WHERE id = 'rc-scope-2'").fetchone()
    assert row[0] == "task"
