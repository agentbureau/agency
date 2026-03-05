from fastapi import APIRouter, Request, HTTPException
from agency.models.tasks import TaskRequest, AgentResponse, EvaluatorResponse
from agency.models.evaluations import EvaluationReport

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=201)
def create_task(req: TaskRequest, request: Request):
    """Register a task and return its ID."""
    from agency.utils.ids import new_uuid
    task_id = new_uuid()
    # Store task description in app state for retrieval
    if not hasattr(request.app.state, "tasks"):
        request.app.state.tasks = {}
    request.app.state.tasks[task_id] = req.model_dump()
    return {"task_id": task_id}


@router.get("/{task_id}/agent", response_model=AgentResponse)
def get_task_agent(task_id: str, request: Request):
    """Return the assigned agent prompt for a task."""
    from agency.engine.assigner import assign_agent
    tasks = getattr(request.app.state, "tasks", {})
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks[task_id]
    return assign_agent(request.app.state.db, task_id, task)


@router.get("/{task_id}/evaluator", response_model=EvaluatorResponse)
def get_task_evaluator(task_id: str, request: Request):
    """Return the evaluator prompt with baked-in callback JWT."""
    import os
    from agency.engine.evaluator import build_evaluator
    tasks = getattr(request.app.state, "tasks", {})
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks[task_id]
    secret = os.environ.get("AGENCY_JWT_SECRET", "")
    instance_id = str(request.app.state.state_dir)
    return build_evaluator(request.app.state.db, task_id, task, secret, instance_id)


@router.post("/{task_id}/evaluation", status_code=202)
def submit_evaluation(task_id: str, report: EvaluationReport, request: Request):
    """Receive an evaluation callback and record it."""
    from agency.db.evaluations import enqueue_evaluation
    import json
    enqueue_evaluation(request.app.state.db, json.dumps(report.model_dump()))
    return {"status": "accepted", "task_id": task_id}
