import os
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
    # jwt_secret stored in app.state after Task 11; fall back to env var for compat
    secret = getattr(request.app.state, "jwt_secret",
                     os.environ.get("AGENCY_JWT_SECRET", ""))
    instance_id = str(request.app.state.state_dir)
    return build_evaluator(request.app.state.db, task_id, task_for_assigner, secret, instance_id)


@router.post("/{task_id}/evaluation", status_code=202)
def submit_evaluation(task_id: str, report: EvaluationReport, request: Request):
    from agency.db.evaluations import enqueue_evaluation
    import json
    enqueue_evaluation(request.app.state.db, json.dumps(report.model_dump()))
    return {"status": "accepted", "task_id": task_id}


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
