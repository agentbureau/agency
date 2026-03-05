import sqlite3
from agency.db.migrations import migration


@migration
def create_initial_schema(conn: sqlite3.Connection) -> None:
    # Placeholder — full table definitions added in Task 6
    pass
