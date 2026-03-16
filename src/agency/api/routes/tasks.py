from fastapi import APIRouter, Request, HTTPException
from agency.models.tasks import TaskRequest, AgentResponse, EvaluatorResponse
from agency.models.evaluations import EvaluationReport
from agency.db.tasks import create_task, get_task, set_task_composition

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=201)
def create_task_route(req: TaskRequest, request: Request):
    tid = create_task(
        request.app.state.db,
        description=req.task_description,
        output_format=req.output_format,
        output_structure=req.output_structure,
        clarification_behaviour=req.clarification_behaviour,
        client_id=req.client_id,
        project_id=req.project_id,
    )
    return {"task_id": tid}


@router.get("/{task_id}/agent", response_model=AgentResponse)
def get_task_agent(task_id: str, request: Request):
    from agency.engine.assigner import assign_agent
    from agency.utils.errors import PrimitiveStoreEmpty

    task = get_task(request.app.state.db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Normalize: assign_agent expects task_description; SQLite stores as description
    task_for_assigner = {**task, "task_description": task.get("description", "")}
    try:
        result = assign_agent(request.app.state.db, task_id, task_for_assigner)
    except PrimitiveStoreEmpty:
        _notify_empty_primitives(request, task.get("project_id"))
        raise HTTPException(
            status_code=503,
            detail={"error": "primitive_store_empty",
                    "message": "No primitives installed. Run 'agency primitives install'."}
        )
    set_task_composition(request.app.state.db, task_id, result["agent_id"])
    return result


@router.get("/{task_id}/evaluator", response_model=EvaluatorResponse)
def get_task_evaluator(task_id: str, request: Request):
    from agency.engine.evaluator import build_evaluator
    task = get_task(request.app.state.db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task_for_assigner = {**task, "task_description": task.get("description", "")}
    private_key = getattr(request.app.state, "private_key", None)
    instance_id = str(request.app.state.state_dir)
    return build_evaluator(request.app.state.db, task_id, task_for_assigner, private_key, instance_id)


def _extract_jwt_claims(claims: dict) -> dict:
    """Extract agent metadata from callback JWT claims into evaluation fields."""
    return {
        "evaluator_agent_id": claims.get("evaluator_agent_id"),
        "evaluator_agent_content_hash": claims.get("evaluator_content_hash"),
        "task_agent": claims.get("task_agent_primitive_ids"),
    }


@router.post("/{task_id}/evaluation", status_code=200)
def submit_evaluation(task_id: str, report: EvaluationReport, request: Request):
    import json
    import logging
    from agency.db.idempotency import is_duplicate
    from agency.utils.hashing import content_hash
    from agency.utils.ids import new_uuid as _new_uuid

    logger = logging.getLogger(__name__)

    task = get_task(request.app.state.db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={
            "error": "not_found",
            "message": f"Task not found for agency_task_id: {task_id}.",
            "cause": "The ID does not match any task. Most common mistake: passing external_id instead of agency_task_id.",
            "fix": "Check the agency_assign response — use the agency_task_id field.",
        })

    # Dual JWT validation: callback JWT from body
    callback_claims = {}
    if report.callback_jwt:
        from agency.auth.jwt import verify_jwt, is_valid_evaluator_scope
        public_key = getattr(request.app.state, "public_key", None)
        try:
            callback_claims = verify_jwt(report.callback_jwt, public_key)
        except Exception:
            raise HTTPException(status_code=401, detail={
                "error": "authentication_failed",
                "message": "Callback JWT is invalid, expired, or already used.",
                "cause": "Each callback_jwt from agency_evaluator is single-use. This JWT may have expired (24h TTL) or been consumed by a prior submission.",
                "fix": "Call agency_evaluator with agency_task_id to get a new callback_jwt, then call agency_submit_evaluation again.",
            })

        scope = callback_claims.get("scope", "")
        if not is_valid_evaluator_scope(scope):
            raise HTTPException(status_code=401, detail={
                "error": "authentication_failed",
                "message": "Callback JWT has invalid scope.",
            })
        if scope == "task":
            logger.warning("Accepted deprecated scope 'task' on evaluator JWT (grace period)")

        jti = callback_claims.get("jti")
        if jti and is_duplicate(request.app.state.db, jti, task_id):
            raise HTTPException(status_code=401, detail={
                "error": "authentication_failed",
                "message": "Callback JWT is invalid, expired, or already used.",
                "cause": "Each callback_jwt from agency_evaluator is single-use.",
                "fix": "Call agency_evaluator with agency_task_id to get a new callback_jwt.",
            })

    # Merge JWT claims into evaluation
    jwt_metadata = _extract_jwt_claims(callback_claims)
    report.task_id = task_id
    report.evaluator_agent_id = report.evaluator_agent_id or jwt_metadata["evaluator_agent_id"]
    report.evaluator_agent_content_hash = report.evaluator_agent_content_hash or jwt_metadata["evaluator_agent_content_hash"]
    report.task_agent = report.task_agent or jwt_metadata["task_agent"]

    data = json.dumps(report.model_dump(exclude={"callback_jwt"}), ensure_ascii=False, separators=(",", ":"))
    hash_ = content_hash(data)

    # Atomic transaction: enqueue evaluation + record JWT consumption
    conn = request.app.state.db
    jti = callback_claims.get("jti")
    try:
        conn.execute("BEGIN")
        eid = _new_uuid()
        conn.execute(
            """INSERT INTO pending_evaluations
               (id, task_id, evaluator_data, destination, content_hash)
               VALUES (?, ?, ?, ?, ?)""",
            (eid, task_id, data, "agency_instance", content_hash(data)),
        )
        if jti:
            conn.execute(
                "INSERT OR IGNORE INTO consumed_jwts (jwt_id, task_id) VALUES (?, ?)",
                (jti, task_id),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return {"status": "accepted", "content_hash": hash_}


def _notify_empty_primitives(request: Request, project_id: str | None) -> None:
    """Best-effort email notification — errors are logged, never raised."""
    import logging
    try:
        if not project_id:
            return
        from agency.db.projects import get_project
        from agency.utils.email import send_notification
        project = get_project(request.app.state.db, project_id)
        if not project or not project.get("admin_email"):
            return
        cfg = getattr(request.app.state, "config", {})
        send_notification(
            cfg,
            to=project["admin_email"],
            subject="Agency: primitive store is empty — assignment failed",
            body=(
                "Agency tried to assign an agent but no primitives are installed.\n\n"
                "Run 'agency primitives install' to fix this."
            ),
        )
    except Exception as e:
        logging.getLogger(__name__).warning("Failed to send primitive store notification: %s", e)
