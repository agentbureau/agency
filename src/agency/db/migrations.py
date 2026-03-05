import sqlite3
from typing import Callable

MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = []


def migration(fn: Callable[[sqlite3.Connection], None]):
    MIGRATIONS.append(fn)
    return fn


def get_schema_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    return row[0] if row else 0


def run_migrations(conn: sqlite3.Connection) -> None:
    current = get_schema_version(conn)
    for i, migration_fn in enumerate(MIGRATIONS, start=1):
        if i > current:
            migration_fn(conn)
            conn.execute("DELETE FROM schema_version")
            conn.execute("INSERT INTO schema_version VALUES (?)", (i,))
            conn.commit()


# Import schema to register migrations
import agency.db.schema  # noqa: F401, E402
