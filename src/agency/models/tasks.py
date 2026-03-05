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
