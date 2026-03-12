import sqlite3
from agency.db.migrations import migration


PRIMITIVE_COLUMNS = """
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    quality INTEGER NOT NULL DEFAULT 100,
    domain_specificity INTEGER NOT NULL DEFAULT 0,
    domain TEXT NOT NULL DEFAULT '[]',
    origin_instance_id TEXT NOT NULL DEFAULT '00000000-0000-7000-8000-000000000001',
    parent_content_hash TEXT,
    permission_block TEXT NOT NULL DEFAULT '14000000000060400000000006',
    instance_id TEXT NOT NULL,
    client_id TEXT,
    project_id TEXT,
    source_tier TEXT,
    embedding TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
"""


@migration
def create_initial_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS role_components (
            {PRIMITIVE_COLUMNS},
            override_capability TEXT
        );
        CREATE TABLE IF NOT EXISTS desired_outcomes ({PRIMITIVE_COLUMNS});
        CREATE TABLE IF NOT EXISTS trade_off_configs ({PRIMITIVE_COLUMNS});

        CREATE VIEW IF NOT EXISTS primitives AS
            SELECT id, name, description, content_hash, quality, domain_specificity, domain,
                   permission_block, override_capability, origin_instance_id, parent_content_hash,
                   instance_id, client_id, project_id, source_tier, embedding, created_at,
                   'role_component' AS primitive_type
            FROM role_components
        UNION ALL
            SELECT id, name, description, content_hash, quality, domain_specificity, domain,
                   permission_block, NULL AS override_capability, origin_instance_id, parent_content_hash,
                   instance_id, client_id, project_id, source_tier, embedding, created_at,
                   'desired_outcome'
            FROM desired_outcomes
        UNION ALL
            SELECT id, name, description, content_hash, quality, domain_specificity, domain,
                   permission_block, NULL AS override_capability, origin_instance_id, parent_content_hash,
                   instance_id, client_id, project_id, source_tier, embedding, created_at,
                   'trade_off_config'
            FROM trade_off_configs;

        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            role_component_ids TEXT NOT NULL DEFAULT '[]',
            desired_outcome_id TEXT,
            trade_off_config_id TEXT,
            content_hash TEXT NOT NULL UNIQUE,
            permission_block TEXT NOT NULL DEFAULT '14000000000060400000000006',
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
            id              TEXT PRIMARY KEY,
            task_id         TEXT NOT NULL,
            evaluator_data  TEXT NOT NULL,
            content_hash    TEXT NOT NULL,
            destination     TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            last_ping_at    TEXT,
            confirmed_at    TEXT,
            confirmed       INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS issued_tokens (
            jti         TEXT PRIMARY KEY,
            client_id   TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at  TEXT,
            revoked     INTEGER NOT NULL DEFAULT 0,
            revoked_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS primitive_mutations (
            id           TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            field        TEXT NOT NULL,
            old_value    TEXT,
            new_value    TEXT NOT NULL,
            changed_by   TEXT NOT NULL,
            changed_at   TEXT NOT NULL DEFAULT (datetime('now')),
            evidence     TEXT NOT NULL
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
            contact_email TEXT,
            oversight_preference TEXT,
            error_notification_timeout INTEGER,
            llm_provider TEXT,
            llm_model TEXT,
            llm_api_key TEXT,
            homepool_retry_max_interval INTEGER,
            permission_block TEXT NOT NULL DEFAULT '14000000000060400000000006',
            attribution INTEGER,
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
