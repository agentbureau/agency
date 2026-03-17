"""GET /status endpoint — instance health, task state, primitive counts."""
import time

from fastapi import APIRouter, Request

router = APIRouter(tags=["status"])

_start_time = time.time()

DESCRIPTION_PREVIEW_LENGTH = 120


@router.get("/status")
def get_status(request: Request, project_id: str | None = None):
    import importlib.metadata

    from agency.db.projects import list_projects

    conn = request.app.state.db
    cfg = getattr(request.app.state, "config", {})
    default_id = cfg.get("project", {}).get("default_id")

    try:
        version = importlib.metadata.version("agency-engine")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"

    instance_id = cfg.get("instance_id", "")

    projects = list_projects(conn)
    if project_id:
        projects = [p for p in projects if p["id"] == project_id]

    project_summaries = []
    for proj in projects:
        pid = proj["id"]
        # Task state derivation via LEFT JOIN — no state column in DB
        rows = conn.execute(
            """
            SELECT
                t.id AS agency_task_id,
                t.external_id,
                t.description,
                a.content_hash AS agent_hash,
                t.created_at,
                CASE
                    WHEN pe.id IS NULL    THEN 'assigned'
                    WHEN pe.confirmed = 0 THEN 'evaluation_pending'
                    WHEN pe.confirmed = 1 THEN 'evaluation_received'
                END AS state
            FROM tasks t
            LEFT JOIN agents a ON a.id = t.agent_composition_id
            LEFT JOIN pending_evaluations pe ON pe.task_id = t.id
            WHERE t.project_id = ?
            """,
            (pid,),
        ).fetchall()

        total = len(rows)
        assigned = sum(1 for r in rows if r[5] == "assigned")
        pending = sum(1 for r in rows if r[5] == "evaluation_pending")
        received = sum(1 for r in rows if r[5] == "evaluation_received")

        active = [
            {
                "agency_task_id": r[0],
                "external_id": r[1],
                "description_preview": (r[2] or "")[:DESCRIPTION_PREVIEW_LENGTH],
                "agent_hash": r[3] or "",
                "state": r[5],
                "created_at": r[4],
            }
            for r in rows
            if r[5] in ("assigned", "evaluation_pending")
        ]

        project_summaries.append(
            {
                "id": pid,
                "name": proj["name"],
                "is_default": pid == default_id,
                "task_summary": {
                    "total": total,
                    "assigned": assigned,
                    "evaluation_pending": pending,
                    "evaluation_received": received,
                },
                "active_tasks": active,
            }
        )

    # Primitive counts
    rc = conn.execute("SELECT COUNT(*) FROM role_components").fetchone()[0]
    do = conn.execute("SELECT COUNT(*) FROM desired_outcomes").fetchone()[0]
    tc = conn.execute("SELECT COUNT(*) FROM trade_off_configs").fetchone()[0]
    eligible = conn.execute(
        "SELECT COUNT(*) FROM primitives WHERE quality > 90"
    ).fetchone()[0]

    return {
        "instance_id": instance_id,
        "server_version": version,
        "uptime_seconds": int(time.time() - _start_time),
        "projects": project_summaries,
        "primitive_counts": {
            "role_components": rc,
            "desired_outcomes": do,
            "trade_off_configs": tc,
            "eligible": eligible,
        },
    }
