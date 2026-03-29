"""Evaluation cascade and assignment tracking (v1.2.4 Issues 23+25)."""
import json
import sqlite3
from datetime import datetime, timezone


def propagate_evaluation_to_primitives(
    conn: sqlite3.Connection,
    task_id: str,
    evaluation_id: str,
    score: float | None,
) -> int:
    """Propagate a composition-level score to per-primitive performance records.

    v1.2.4 scope: all three primitive types (equal propagation).
    Returns count of primitives updated.
    """
    if score is None:
        return 0

    score = float(score)

    # Idempotency: check if this evaluation was already cascaded
    already = conn.execute(
        "SELECT 1 FROM cascaded_evaluation_ids WHERE evaluation_id = ?",
        (evaluation_id,),
    ).fetchone()
    if already:
        return 0

    # Look up all primitive IDs from the composition via the task's agent
    row = conn.execute(
        """SELECT a.role_component_ids, a.desired_outcome_id, a.trade_off_config_id
           FROM tasks t
           JOIN agents a ON a.id = t.agent_composition_id
           WHERE t.id = ?""",
        (task_id,),
    ).fetchone()
    if not row:
        return 0

    now = datetime.now(timezone.utc).isoformat()
    updated = 0

    # Propagate to all primitive types — equal propagation
    primitives_to_update: list[tuple[str, str]] = []
    if row[0]:  # role_component_ids (JSON array)
        for rc_id in json.loads(row[0]):
            primitives_to_update.append((rc_id, "role_component"))
    if row[1]:  # desired_outcome_id (single UUID)
        primitives_to_update.append((row[1], "desired_outcome"))
    if row[2]:  # trade_off_config_id (single UUID)
        primitives_to_update.append((row[2], "trade_off_config"))

    for prim_id, prim_type in primitives_to_update:
        conn.execute("""
            INSERT INTO primitive_performance
                (primitive_id, primitive_type, evaluation_count, avg_score,
                 last_evaluation_id, last_evaluation_at)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(primitive_id, primitive_type) DO UPDATE SET
                avg_score = (avg_score * evaluation_count + ?) / (evaluation_count + 1),
                evaluation_count = evaluation_count + 1,
                last_evaluation_id = ?,
                last_evaluation_at = ?
        """, (prim_id, prim_type, score, evaluation_id, now,
              score, evaluation_id, now))
        updated += 1

    # Record this evaluation as cascaded (idempotency tracking)
    conn.execute(
        "INSERT OR IGNORE INTO cascaded_evaluation_ids (evaluation_id, cascaded_at) VALUES (?, ?)",
        (evaluation_id, now),
    )
    conn.commit()
    return updated


def increment_assignment_counts(
    conn: sqlite3.Connection,
    role_component_ids: list[str],
    desired_outcome_id: str | None,
    trade_off_config_id: str | None,
) -> None:
    """Increment assignment_count for all selected primitives (Issue 25)."""
    now = datetime.now(timezone.utc).isoformat()
    primitives = [
        (rid, "role_component") for rid in role_component_ids
    ]
    if desired_outcome_id:
        primitives.append((desired_outcome_id, "desired_outcome"))
    if trade_off_config_id:
        primitives.append((trade_off_config_id, "trade_off_config"))

    for pid, ptype in primitives:
        conn.execute("""
            INSERT INTO primitive_performance
                (primitive_id, primitive_type, assignment_count, last_assigned_at)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(primitive_id, primitive_type) DO UPDATE SET
                assignment_count = assignment_count + 1,
                last_assigned_at = ?
        """, (pid, ptype, now, now))

    conn.commit()
