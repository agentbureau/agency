"""Starter primitive distribution: fetch CSV from GitHub, reconcile with local store."""
import csv
import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import click
import httpx

from agency.db.migrations import run_migrations
from agency.db.primitives import (
    AGENTBUREAU_INSTANCE_ID,
    PRIMITIVE_TABLES,
    TYPE_TO_TABLE,
    insert_primitive,
)
from agency.constants import GITHUB_ORG, GITHUB_REPO
from agency.utils.hashing import content_hash
from agency.utils.ids import new_uuid

STARTER_CSV_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_ORG}/{GITHUB_REPO}/main/primitives/starter.csv"
)
QUALITY_THRESHOLD = 90

REQUIRED_COLUMNS = {"type", "name", "description"}
VALID_TYPES = {"role_component", "desired_outcome", "trade_off_config"}


def _fetch_csv(url: str) -> list[dict]:
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    return list(reader)


def _parse_domain(raw: str) -> str:
    """Convert comma-separated CSV domain to JSON array string."""
    if not raw or not raw.strip():
        return "[]"
    parts = [d.strip() for d in raw.split(",") if d.strip()]
    return json.dumps(parts)


def _get_db(state_dir: Path | None = None) -> sqlite3.Connection:
    if state_dir is None:
        state_dir = Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))
    conn = sqlite3.connect(state_dir / "agency.db")
    run_migrations(conn)
    return conn


def _get_existing_by_hash(conn: sqlite3.Connection) -> dict[str, dict]:
    """Return {content_hash: {table, quality, domain_specificity, domain}} for all primitives."""
    existing = {}
    for table in PRIMITIVE_TABLES:
        rows = conn.execute(
            f"SELECT content_hash, quality, domain_specificity, domain, scope FROM {table}"
        ).fetchall()
        for row in rows:
            existing[row[0]] = {
                "table": table,
                "quality": row[1],
                "domain_specificity": row[2],
                "domain": row[3],
                "scope": row[4],
            }
    return existing


def _record_mutation(
    conn: sqlite3.Connection,
    chash: str,
    field: str,
    old_value: str | None,
    new_value: str,
    changed_by: str,
) -> None:
    conn.execute(
        """INSERT INTO primitive_mutations
           (id, content_hash, field, old_value, new_value, changed_by, evidence)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            new_uuid(),
            chash,
            field,
            old_value,
            new_value,
            changed_by,
            json.dumps({
                "source": "upstream_csv",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }),
        ),
    )


def install_from_csv(
    rows: list[dict],
    conn: sqlite3.Connection,
    instance_id: str,
) -> dict:
    """Insert primitives from parsed CSV rows. Returns stats dict."""
    existing = _get_existing_by_hash(conn)
    stats = {"inserted": 0, "skipped": 0, "failed": 0, "failed_rows": []}

    for row_num, row in enumerate(rows, start=1):
        try:
            quality = int(row.get("quality", 100))
            if quality <= QUALITY_THRESHOLD:
                stats["skipped"] += 1
                continue

            ptype = row["type"]
            table = TYPE_TO_TABLE.get(ptype)
            if not table:
                stats["skipped"] += 1
                continue

            desc = row["description"]
            chash = content_hash(desc)
            if chash in existing:
                stats["skipped"] += 1
                continue

            domain_csv = row.get("domain", "")
            domain_json = _parse_domain(domain_csv)

            insert_primitive(
                conn,
                table,
                description=desc,
                instance_id=instance_id,
                name=row.get("name", ""),
                quality=quality,
                domain_specificity=int(row.get("domain_specificity", 0)),
                domain=domain_json,
                origin_instance_id=row.get("origin_instance_id", AGENTBUREAU_INSTANCE_ID),
                parent_content_hash=row.get("parent_content_hash") or None,
                scope=row.get("scope", "task"),
                created_by=row.get("created_by", "human"),
                generation=int(row.get("generation", 0)),
                parent_ids=row.get("parent_ids") or None,
            )
            existing[chash] = {"table": table}
            stats["inserted"] += 1
        except Exception as e:
            conn.rollback()
            stats["failed"] += 1
            stats["failed_rows"].append({
                "row": row_num,
                "name": row.get("name", ""),
                "error": str(e),
            })
            continue

    return stats


def reconcile_from_csv(
    rows: list[dict],
    conn: sqlite3.Connection,
    instance_id: str,
) -> dict:
    """Full reconciliation: insert new, update changed fields, record mutations.

    Per-row commits — a single row failure does not abort remaining rows.
    """
    existing = _get_existing_by_hash(conn)
    stats = {"new": 0, "updated_primitives": 0, "fields_changed": 0,
             "unchanged": 0, "below_threshold": 0, "failed": 0,
             "failed_rows": []}

    for row_num, row in enumerate(rows, start=1):
        try:
            quality = int(row.get("quality", 100))
            ptype = row["type"]
            table = TYPE_TO_TABLE.get(ptype)
            if not table:
                continue

            desc = row["description"]
            chash = content_hash(desc)
            domain_json = _parse_domain(row.get("domain", ""))
            domain_spec = int(row.get("domain_specificity", 0))

            if chash not in existing:
                if quality <= QUALITY_THRESHOLD:
                    stats["below_threshold"] += 1
                    continue
                insert_primitive(
                    conn, table,
                    description=desc,
                    instance_id=instance_id,
                    name=row.get("name", ""),
                    quality=quality,
                    domain_specificity=domain_spec,
                    domain=domain_json,
                    origin_instance_id=row.get("origin_instance_id", AGENTBUREAU_INSTANCE_ID),
                    parent_content_hash=row.get("parent_content_hash") or None,
                    scope=row.get("scope", "task"),
                    created_by=row.get("created_by", "human"),
                    generation=int(row.get("generation", 0)),
                    parent_ids=row.get("parent_ids") or None,
                )
                existing[chash] = {
                    "table": table,
                    "quality": quality,
                    "domain_specificity": domain_spec,
                    "domain": domain_json,
                    "scope": row.get("scope", "task"),
                }
                stats["new"] += 1
            else:
                local = existing[chash]
                changed = False

                if local["quality"] != quality:
                    _record_mutation(conn, chash, "quality",
                                     str(local["quality"]), str(quality),
                                     AGENTBUREAU_INSTANCE_ID)
                    conn.execute(
                        f"UPDATE {local['table']} SET quality = ? WHERE content_hash = ?",
                        (quality, chash),
                    )
                    stats["fields_changed"] += 1
                    changed = True

                if local["domain_specificity"] != domain_spec:
                    _record_mutation(conn, chash, "domain_specificity",
                                     str(local["domain_specificity"]), str(domain_spec),
                                     AGENTBUREAU_INSTANCE_ID)
                    conn.execute(
                        f"UPDATE {local['table']} SET domain_specificity = ? WHERE content_hash = ?",
                        (domain_spec, chash),
                    )
                    stats["fields_changed"] += 1
                    changed = True

                if local["domain"] != domain_json:
                    _record_mutation(conn, chash, "domain",
                                     local["domain"], domain_json,
                                     AGENTBUREAU_INSTANCE_ID)
                    conn.execute(
                        f"UPDATE {local['table']} SET domain = ? WHERE content_hash = ?",
                        (domain_json, chash),
                    )
                    stats["fields_changed"] += 1
                    changed = True

                csv_scope = row.get("scope", "task")
                if local.get("scope", "task") != csv_scope:
                    _record_mutation(conn, chash, "scope",
                                     local.get("scope", "task"), csv_scope,
                                     AGENTBUREAU_INSTANCE_ID)
                    conn.execute(
                        f"UPDATE {local['table']} SET scope = ? WHERE content_hash = ?",
                        (csv_scope, chash),
                    )
                    stats["fields_changed"] += 1
                    changed = True

                if changed:
                    conn.commit()
                    stats["updated_primitives"] += 1
                else:
                    stats["unchanged"] += 1
        except Exception as e:
            conn.rollback()
            stats["failed"] += 1
            stats["failed_rows"].append({
                "row": row_num,
                "name": row.get("name", ""),
                "error": str(e),
            })
            continue

    return stats


@click.group("primitives")
def primitives_command():
    """Manage Agency primitives."""


@primitives_command.command("install")
@click.option("--instance-id", default="default", show_default=True)
def install_primitives_cmd(instance_id: str):
    """Fetch and install the starter primitive set from GitHub."""
    click.echo("Fetching starter primitives from GitHub...")
    try:
        rows = _fetch_csv(STARTER_CSV_URL)
    except Exception as e:
        click.echo(f"Error: Could not fetch starter CSV: {e}")
        raise SystemExit(1)

    conn = _get_db()
    stats = install_from_csv(rows, conn, instance_id)
    conn.close()
    click.echo(f"{stats['inserted']} primitives installed ({stats['skipped']} skipped).")
    if stats["failed"]:
        click.echo(f"\nFailed: {stats['failed']} row(s)")
        for f in stats["failed_rows"]:
            click.echo(f"  Row {f['row']}: {f['error']}")
        click.echo(
            f"\nYour database now contains all {stats['inserted']} successfully "
            f"processed primitives.\nNo action required — failed rows do not "
            f"affect successful rows."
        )


@primitives_command.command("update")
@click.option("--instance-id", default="default", show_default=True)
def update_primitives_cmd(instance_id: str):
    """Fetch latest starter CSV and reconcile with local store."""
    click.echo("Fetching latest primitives from GitHub...")
    try:
        rows = _fetch_csv(STARTER_CSV_URL)
    except Exception as e:
        click.echo(f"Error: Could not fetch starter CSV: {e}")
        raise SystemExit(1)

    conn = _get_db()
    stats = reconcile_from_csv(rows, conn, instance_id)
    conn.close()

    below = ""
    if stats["below_threshold"]:
        below = f" ({stats['below_threshold']} below quality threshold)"
    click.echo(
        f"Primitives updated.\n"
        f"  New:       {stats['new']} installed{below}\n"
        f"  Updated:   {stats['fields_changed']} fields changed across "
        f"{stats['updated_primitives']} primitives\n"
        f"  Unchanged: {stats['unchanged']}"
    )
    if stats.get("failed"):
        click.echo(f"  Failed:    {stats['failed']} row(s)\n")
        click.echo("Failed rows:")
        for f in stats["failed_rows"]:
            click.echo(f"  Row {f['row']}: {f['error']}")
        click.echo(
            f"\nYour database now contains all {stats['new']} successfully "
            f"processed primitives.\nNo action required — failed rows do not "
            f"affect successful rows.\nEach row is committed independently. "
            f"The failed row will be retried\non next update; if the upstream "
            f"CSV still contains the duplicate,\nit will fail again with the "
            f"same message."
        )


@primitives_command.command("list")
@click.option("--table", default="role_components",
              type=click.Choice(["role_components", "desired_outcomes", "trade_off_configs"]))
def list_primitives(table: str):
    """List stored primitives."""
    conn = _get_db()
    rows = conn.execute(f"SELECT id, description, quality FROM {table}").fetchall()
    conn.close()
    if not rows:
        click.echo(f"No {table} found.")
        return
    for rid, desc, quality in rows:
        click.echo(f"  {rid}  [q={quality}] {desc[:70]}")


def _read_local_csv(path: str) -> list[dict]:
    """Read and parse a local CSV file."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _validate_csv_row(row: dict, row_num: int) -> tuple[bool, str | None]:
    """Return (valid, error_message)."""
    for col in REQUIRED_COLUMNS:
        if not row.get(col, "").strip():
            return False, f"Row {row_num}: missing or empty required column '{col}'"
    if row["type"] not in VALID_TYPES:
        return False, f"Row {row_num}: invalid type '{row['type']}' — must be one of: {', '.join(sorted(VALID_TYPES))}"
    return True, None


@primitives_command.command("import")
@click.argument("path", type=click.Path(exists=True, readable=True))
@click.option("--instance-id", default="default", show_default=True)
@click.option("--dry-run", is_flag=True, help="Validate and report without inserting.")
def import_primitives_cmd(path: str, instance_id: str, dry_run: bool):
    """Import primitives from a local CSV file."""
    try:
        rows = _read_local_csv(path)
    except Exception as e:
        click.echo(f"Error reading CSV: {e}")
        raise SystemExit(1)

    if not rows:
        click.echo("CSV file is empty.")
        return

    # Check that 'name' column exists in the CSV
    if "name" not in rows[0]:
        click.echo(
            "Error: name column is required — run the extraction skill to "
            "generate names, or add them manually."
        )
        raise SystemExit(1)

    conn = None if dry_run else _get_db()
    existing = {} if dry_run else _get_existing_by_hash(conn)
    stats = {"added": 0, "skipped": 0, "failed": 0, "failed_rows": []}

    for row_num, row in enumerate(rows, start=1):
        valid, err = _validate_csv_row(row, row_num)
        if not valid:
            stats["failed"] += 1
            stats["failed_rows"].append({"row": row_num, "error": err})
            continue

        desc = row["description"]
        chash = content_hash(desc)
        if chash in existing:
            stats["skipped"] += 1
            continue

        if dry_run:
            stats["added"] += 1
            continue

        try:
            table = TYPE_TO_TABLE[row["type"]]
            domain_json = _parse_domain(row.get("domain", ""))
            insert_primitive(
                conn, table,
                description=desc,
                instance_id=instance_id,
                name=row.get("name", ""),
                quality=int(row.get("quality", 100)),
                domain_specificity=int(row.get("domain_specificity", 0)),
                domain=domain_json,
                origin_instance_id=row.get("origin_instance_id", AGENTBUREAU_INSTANCE_ID),
                parent_content_hash=row.get("parent_content_hash") or None,
                scope=row.get("scope", "task"),
                # Intentionally overrides CSV created_by — import command records provenance, not origin
                created_by="import",
                generation=0,
                parent_ids=row.get("parent_ids") or None,
            )
            existing[chash] = {"table": table}
            stats["added"] += 1
        except Exception as e:
            conn.rollback()
            stats["failed"] += 1
            stats["failed_rows"].append({"row": row_num, "error": str(e)})

    if conn:
        conn.close()

    mode = "(dry run) " if dry_run else ""
    click.echo(f"{mode}Import complete: {stats['added']} added, {stats['skipped']} skipped (duplicate), {stats['failed']} failed.")
    if stats["failed_rows"]:
        click.echo("\nFailed rows:")
        for f in stats["failed_rows"]:
            click.echo(f"  {f['error']}")
