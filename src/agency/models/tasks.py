from pydantic import BaseModel


class TaskRequest(BaseModel):
    task_description: str
    output_structure: str = "structured"
    output_format: str = "json"
    clarification_behaviour: str = "ask"
    client_id: str | None = None
    project_id: str | None = None


class AgentResponse(BaseModel):
    agent_id: str
    content_hash: str
    template_id: str
    rendered_prompt: str


class EvaluatorResponse(BaseModel):
    evaluator_agent_id: str
    content_hash: str
    template_id: str
    rendered_prompt: str
    callback_jwt: str


class BatchTaskRequest(BaseModel):
    external_id: str | None = None
    description: str
    skills: list[str] = []
    deliverables: list[str] = []
    output_format: str | None = None
    output_structure: str | None = None


class BatchAssignRequest(BaseModel):
    tasks: list[BatchTaskRequest]


class AgentDefinition(BaseModel):
    rendered_prompt: str
    content_hash: str
    template_id: str
    primitive_ids: dict
    agent_id: str
    composition_fitness: dict | None = None


class ProjectVerification(BaseModel):
    project_id: str
    project_name: str | None
    prompt: str


class BatchAssignResponse(BaseModel):
    assignments: dict  # external_id -> {agency_task_id, agent_hash}
    agents: dict       # agent_hash -> AgentDefinition
    project_verification: ProjectVerification | None = None
