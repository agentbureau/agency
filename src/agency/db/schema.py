import sqlite3
from agency.db.migrations import migration


PRIMITIVE_COLUMNS = """
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    permission_block TEXT NOT NULL DEFAULT ('1400000000006' || '1400000000006'),
    override_capability TEXT,
    instance_id TEXT NOT NULL,
    client_id TEXT,
    project_id TEXT,
    former_agents TEXT DEFAULT '[]',
    evaluations_received TEXT DEFAULT '{}',
    source_tier TEXT,
    embedding TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
"""


@migration
def create_initial_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS role_components ({PRIMITIVE_COLUMNS});
        CREATE TABLE IF NOT EXISTS desired_outcomes ({PRIMITIVE_COLUMNS});
        CREATE TABLE IF NOT EXISTS trade_off_configs ({PRIMITIVE_COLUMNS});

        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            role_component_ids TEXT NOT NULL DEFAULT '[]',
            desired_outcome_id TEXT,
            trade_off_config_id TEXT,
            content_hash TEXT NOT NULL UNIQUE,
            permission_block TEXT NOT NULL DEFAULT ('1400000000006' || '1400000000006'),
            performance_history TEXT DEFAULT '[]',
            instance_id TEXT NOT NULL,
            client_id TEXT,
            project_id TEXT,
            source_tier TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS templates (
            id TEXT PRIMARY KEY,
            template_type TEXT NOT NULL CHECK(template_type IN ('task_agent','evaluator')),
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE,
            performance_history TEXT DEFAULT '[]',
            instance_id TEXT NOT NULL,
            client_id TEXT,
            project_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pending_evaluations (
            id TEXT PRIMARY KEY,
            evaluator_data TEXT NOT NULL,
            destination TEXT NOT NULL DEFAULT 'agency_instance'
                CHECK(destination IN ('agency_instance','home_pool')),
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_ping_at TEXT,
            confirmed_at TEXT,
            confirmed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS consumed_jwts (
            jwt_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            received_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (jwt_id, task_id)
        );

        CREATE TABLE IF NOT EXISTS seen_announcement_ids (
            id TEXT PRIMARY KEY,
            section TEXT NOT NULL,
            seen_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
    """)


@migration
def add_projects_and_tasks(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            client_id TEXT,
            description TEXT,
            admin_email TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            external_id TEXT,
            project_id TEXT,
            description TEXT NOT NULL,
            output_format TEXT,
            output_structure TEXT,
            clarification_behaviour TEXT,
            client_id TEXT,
            agent_composition_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );
    """)
