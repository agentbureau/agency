from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    client_id: str | None = None
    description: str | None = None


@router.post("", status_code=201)
def create_project(req: ProjectCreate, request: Request):
    from agency.utils.ids import new_uuid
    project_id = new_uuid()
    if not hasattr(request.app.state, "projects"):
        request.app.state.projects = {}
    request.app.state.projects[project_id] = req.model_dump()
    return {"project_id": project_id, **req.model_dump()}


@router.get("/{project_id}")
def get_project(project_id: str, request: Request):
    projects = getattr(request.app.state, "projects", {})
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project_id": project_id, **projects[project_id]}
