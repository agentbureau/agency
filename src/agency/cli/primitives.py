"""
Tasks 35 & 37: Starter primitive set installer and primitives update.
"""
import click

STARTER_PRIMITIVES = {
    "role_components": [
        "Evaluate task output for quality, accuracy, and completeness",
        "Assign and prioritise tasks based on urgency and importance",
        "Synthesise information from multiple sources into a coherent summary",
        "Review work against specified criteria and provide structured feedback",
        "Generate structured reports from unstructured input data",
        "Identify gaps, errors, or inconsistencies in provided content",
        "Translate requirements into step-by-step execution plans",
        "Monitor progress and flag deviations from expected outcomes",
    ],
    "desired_outcomes": [
        "Produce a structured evaluation report with a numeric score",
        "Deliver a clear, concise summary suitable for decision-making",
        "Generate an actionable plan with defined steps and owners",
        "Provide a quality assessment with specific improvement recommendations",
        "Complete the task with documented reasoning for each decision",
    ],
    "trade_off_configs": [
        "Prioritise accuracy and rigour over speed of completion",
        "Balance thoroughness with efficiency; flag uncertainty rather than guess",
        "Optimise for brevity: produce the minimum viable output",
        "Maximise coverage: address all aspects even if some are uncertain",
    ],
}

EXTENDED_PRIMITIVES = {
    "role_components": [
        "Apply domain-specific expertise to validate technical claims",
        "Cross-reference outputs against authoritative external sources",
        "Decompose complex tasks into independently executable subtasks",
        "Negotiate trade-offs between competing objectives explicitly",
    ],
    "desired_outcomes": [
        "Return machine-readable JSON conforming to the specified schema",
        "Produce a ranked list of options with justification for each",
    ],
    "trade_off_configs": [
        "Weight consistency over novelty: prefer established approaches",
        "Prefer explicit uncertainty disclosure over confident guessing",
    ],
}


@click.group("primitives")
def primitives_command():
    """Manage Agency primitives."""


@primitives_command.command("install")
@click.option("--extended", is_flag=True, default=False,
              help="Also install the extended primitive set")
@click.option("--instance-id", default="default", show_default=True)
def install_primitives(extended: bool, instance_id: str):
    """Install the starter primitive set (content-hash deduped)."""
    import os, sqlite3
    from pathlib import Path
    from agency.db.migrations import run_migrations
    from agency.db.primitives import insert_primitive

    state_dir = Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))
    conn = sqlite3.connect(state_dir / "agency.db")
    run_migrations(conn)

    sets = [STARTER_PRIMITIVES]
    if extended:
        sets.append(EXTENDED_PRIMITIVES)

    inserted = skipped = 0
    for pset in sets:
        for table, descs in pset.items():
            for desc in descs:
                try:
                    insert_primitive(conn, table, desc, instance_id=instance_id)
                    inserted += 1
                except Exception:
                    skipped += 1

    click.echo(f"✓ Installed {inserted} primitives ({skipped} already present)")


@primitives_command.command("update")
@click.option("--instance-id", default="default", show_default=True)
def update_primitives(instance_id: str):
    """Add any new primitives from the latest starter set (add-only, no deletions)."""
    import os, sqlite3
    from pathlib import Path
    from agency.db.migrations import run_migrations
    from agency.db.primitives import insert_primitive

    state_dir = Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))
    conn = sqlite3.connect(state_dir / "agency.db")
    run_migrations(conn)

    inserted = skipped = 0
    for table, descs in {**STARTER_PRIMITIVES, **EXTENDED_PRIMITIVES}.items():
        for desc in descs:
            try:
                insert_primitive(conn, table, desc, instance_id=instance_id)
                inserted += 1
            except Exception:
                skipped += 1

    click.echo(f"✓ Added {inserted} new primitives ({skipped} already present)")


@primitives_command.command("list")
@click.option("--table", default="role_components",
              type=click.Choice(["role_components", "desired_outcomes", "trade_off_configs"]))
def list_primitives(table: str):
    """List stored primitives."""
    import os, sqlite3
    from pathlib import Path
    from agency.db.migrations import run_migrations

    state_dir = Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))
    conn = sqlite3.connect(state_dir / "agency.db")
    run_migrations(conn)
    rows = conn.execute(f"SELECT id, description FROM {table}").fetchall()
    if not rows:
        click.echo(f"No {table} found.")
        return
    for rid, desc in rows:
        click.echo(f"  {rid}  {desc[:80]}")
