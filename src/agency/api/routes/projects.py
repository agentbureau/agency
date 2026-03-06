from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from agency.db.projects import create_project, get_project

router = APIRouter(prefix="/projects", tags=["projects"])


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
