from typing import Optional, Literal
from pydantic import BaseModel, field_validator


VALID_SCORE_TYPES = ("binary", "rubric", "likert", "percentage")


class EvaluationReport(BaseModel):
    output: str
    callback_jwt: Optional[str] = None
    task_id: Optional[str] = None
    evaluator_agent_id: Optional[str] = None
    evaluator_agent_content_hash: Optional[str] = None
    task_completed: Optional[bool] = None
    score_type: Optional[Literal["binary", "rubric", "likert", "percentage"]] = None
    score: Optional[int] = None
    time_taken_seconds: Optional[float] = None
    estimated_tokens: Optional[int] = None
    task_agent: Optional[dict] = None
    evaluator_agent: Optional[dict] = None
    dimensional_scores: Optional[dict] = None

    @field_validator("score")
    @classmethod
    def score_in_range(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError("score must be between 0 and 100")
        return v
