from typing import Optional
from pydantic import BaseModel


class EvaluationReport(BaseModel):
    output: str
    task_id: Optional[str] = None
    evaluator_agent_id: Optional[str] = None
    evaluator_agent_content_hash: Optional[str] = None
    task_completed: Optional[bool] = None
    score_type: Optional[str] = None
    score: Optional[float] = None
    time_taken_seconds: Optional[float] = None
    estimated_tokens: Optional[int] = None
    task_agent: Optional[dict] = None
    evaluator_agent: Optional[dict] = None
