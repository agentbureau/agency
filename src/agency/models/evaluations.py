from pydantic import BaseModel


class EvaluationReport(BaseModel):
    task_id: str
    evaluator_agent_id: str
    evaluator_agent_content_hash: str
    task_completed: bool
    score_type: str
    score: float
    time_taken_seconds: float
    estimated_tokens: int
    task_agent: dict
    evaluator_agent: dict
