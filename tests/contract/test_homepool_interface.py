"""
Contract tests for the home pool interface.
These verify that Agency's outputs conform to the v2 spec
before the home pool server exists.
Run against a local mock HTTPX server.
"""
import pytest
from agency.auth.keypair import generate_keypair, load_private_key, load_public_key
from agency.auth.jwt import create_evaluator_jwt, verify_jwt


@pytest.fixture
def keypair(tmp_path):
    priv = str(tmp_path / "key.pem")
    pub = str(tmp_path / "key.pub.pem")
    generate_keypair(priv, pub)
    return load_private_key(priv), load_public_key(pub)


def test_evaluator_jwt_contains_required_attribution_fields(keypair):
    private_key, public_key = keypair
    token = create_evaluator_jwt(
        private_key, instance_id="i", client_id="c",
        project_id="p", task_id="t",
    )
    payload = verify_jwt(token, public_key)
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


def test_jwt_expiry_is_enforced(keypair):
    """Expired JWTs must be rejected — home pool will verify on receipt."""
    import time
    private_key, public_key = keypair
    now = int(time.time())
    token = create_evaluator_jwt(
        private_key, instance_id="i", client_id="c",
        project_id="p", task_id="t", exp_seconds=-1
    )
    import jwt as pyjwt
    with pytest.raises(pyjwt.exceptions.ExpiredSignatureError):
        verify_jwt(token, public_key)
