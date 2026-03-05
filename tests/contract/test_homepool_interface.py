"""
Contract tests for the home pool interface.
These verify that Agency's outputs conform to the v2 spec
before the home pool server exists.
Run against a local mock HTTPX server.
"""
from agency.auth.jwt import create_evaluator_jwt, verify_jwt


def test_evaluator_jwt_contains_required_attribution_fields():
    token = create_evaluator_jwt(
        secret="s" * 32, instance_id="i", client_id="c",
        project_id="p", task_id="t", expiry_seconds=3600
    )
    payload = verify_jwt("s" * 32, token)
    for field in ["instance_id", "client_id", "project_id", "task_id"]:
        assert field in payload, f"JWT missing home pool attribution field: {field}"


def test_evaluation_report_has_required_home_pool_fields():
    """Evaluation report must carry fields the home pool needs for attribution."""
    from agency.models.evaluations import EvaluationReport
    report = EvaluationReport(
        task_id="t", evaluator_agent_id="e", evaluator_agent_content_hash="h",
        task_completed=True, score_type="percentage", score=85,
        time_taken_seconds=30, estimated_tokens=500,
        task_agent={"model_provider": "anthropic", "model_name": "claude-sonnet-4-6"},
        evaluator_agent={"model_provider": "openai", "model_name": "gpt-4o"},
    )
    d = report.model_dump()
    for field in ["task_id", "evaluator_agent_id", "evaluator_agent_content_hash"]:
        assert field in d


def test_evaluation_report_score_is_numeric():
    from agency.models.evaluations import EvaluationReport
    report = EvaluationReport(
        task_id="t", evaluator_agent_id="e", evaluator_agent_content_hash="h",
        task_completed=True, score_type="percentage", score=72.5,
        time_taken_seconds=45, estimated_tokens=800,
        task_agent={"model_provider": "anthropic", "model_name": "claude-sonnet-4-6"},
        evaluator_agent={"model_provider": "anthropic", "model_name": "claude-sonnet-4-6"},
    )
    assert isinstance(report.score, float)


def test_jwt_expiry_is_enforced():
    """Expired JWTs must be rejected — home pool will verify on receipt."""
    from agency.auth.jwt import JWTError
    import pytest
    token = create_evaluator_jwt(
        secret="s" * 32, instance_id="i", client_id="c",
        project_id="p", task_id="t", expiry_seconds=-1
    )
    try:
        verify_jwt("s" * 32, token)
        assert False, "Should have raised JWTError"
    except JWTError as e:
        assert "expired" in str(e)
