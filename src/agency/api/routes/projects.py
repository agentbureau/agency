import logging
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from agency.db.projects import create_project, get_project
from agency.db.tasks import create_task, set_task_composition
from agency.models.tasks import BatchAssignRequest, BatchAssignResponse
from agency.utils.errors import PrimitiveStoreEmpty

router = APIRouter(prefix="/projects", tags=["projects"])

log = logging.getLogger(__name__)


class ProjectCreate(BaseModel):
    name: str
    client_id: str | None = None
    description: str | None = None
    admin_email: str | None = None


@router.post("", status_code=201)
def create_project_route(req: ProjectCreate, request: Request):
    pid = create_project(
        request.app.state.db,
        name=req.name,
        client_id=req.client_id,
        description=req.description,
        admin_email=req.admin_email,
    )
    return {"project_id": pid, **req.model_dump()}


@router.get("/{project_id}")
def get_project_route(project_id: str, request: Request):
    project = get_project(request.app.state.db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/{project_id}/assign", response_model=BatchAssignResponse)
def batch_assign(project_id: str, req: BatchAssignRequest, request: Request):
    from agency.engine.assigner import assign_agents_batch

    project = get_project(request.app.state.db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Create task records
    task_id_map = {}
    for task in req.tasks:
        tid = create_task(
            request.app.state.db,
            description=task.description,
            external_id=task.external_id,
            project_id=project_id,
        )
        if task.external_id:
            task_id_map[task.external_id] = tid

    try:
        packet = assign_agents_batch(req.tasks, request.app.state.db,
                                     getattr(request.app.state, "config", {}))
    except PrimitiveStoreEmpty:
        _notify_empty_primitives(request, project)
        raise HTTPException(
            status_code=503,
            detail={"error": "primitive_store_empty",
                    "message": "No primitives installed. Run 'agency primitives install'."}
        )

    # Patch agency_task_ids into packet from our task records
    for ext_id, assignment in packet["assignments"].items():
        if ext_id in task_id_map:
            assignment["agency_task_id"] = task_id_map[ext_id]
            set_task_composition(
                request.app.state.db,
                task_id_map[ext_id],
                assignment["agent_hash"],
            )

    return packet


def _notify_empty_primitives(request: Request, project: dict) -> None:
    try:
        admin_email = project.get("admin_email")
        if not admin_email:
            return
        from agency.utils.email import send_notification
        cfg = getattr(request.app.state, "config", {})
        send_notification(
            cfg,
            to=admin_email,
            subject="Agency: primitive store is empty — assignment failed",
            body="No primitives are installed. Run 'agency primitives install' to fix this.",
        )
    except Exception as e:
        log.warning("Failed to send primitive store notification: %s", e)
