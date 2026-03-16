import time
import pytest
import jwt as pyjwt
from agency.auth.keypair import generate_keypair, load_private_key, load_public_key
from agency.auth.jwt import create_jwt, verify_jwt, create_evaluator_jwt
from agency.utils.ids import generate_uuid_v7


@pytest.fixture
def keypair(tmp_path):
    priv = str(tmp_path / "key.pem")
    pub = str(tmp_path / "key.pub.pem")
    generate_keypair(priv, pub)
    return load_private_key(priv), load_public_key(pub)


def test_create_jwt_returns_string(keypair):
    private_key, _ = keypair
    token = create_jwt(private_key, "inst-1", "client-1", generate_uuid_v7())
    assert isinstance(token, str)


def test_create_jwt_algorithm_is_eddsa(keypair):
    private_key, public_key = keypair
    token = create_jwt(private_key, "inst-1", "client-1", generate_uuid_v7())
    header = pyjwt.get_unverified_header(token)
    assert header["alg"] == "EdDSA"


def test_verify_jwt_returns_payload(keypair):
    private_key, public_key = keypair
    jti = generate_uuid_v7()
    token = create_jwt(private_key, "inst-1", "client-1", jti)
    payload = verify_jwt(token, public_key)
    assert payload["instance_id"] == "inst-1"
    assert payload["client_id"] == "client-1"
    assert payload["jti"] == jti
    assert payload["scope"] == "task"
    assert "iat" in payload


def test_verify_jwt_wrong_key_raises(keypair, tmp_path):
    private_key, _ = keypair
    priv2 = str(tmp_path / "key2.pem")
    pub2 = str(tmp_path / "key2.pub.pem")
    generate_keypair(priv2, pub2)
    wrong_public_key = load_public_key(pub2)
    token = create_jwt(private_key, "inst-1", "client-1", generate_uuid_v7())
    with pytest.raises(pyjwt.InvalidTokenError):
        verify_jwt(token, wrong_public_key)


def test_create_jwt_no_exp_when_not_provided(keypair):
    private_key, public_key = keypair
    token = create_jwt(private_key, "inst-1", "client-1", generate_uuid_v7())
    payload = verify_jwt(token, public_key)
    assert "exp" not in payload


def test_create_jwt_with_exp(keypair):
    private_key, public_key = keypair
    exp = int(time.time()) + 3600
    token = create_jwt(private_key, "inst-1", "client-1", generate_uuid_v7(), exp=exp)
    payload = verify_jwt(token, public_key)
    assert payload["exp"] == exp


def test_create_evaluator_jwt_has_required_claims(keypair):
    """v1.2.1: evaluator JWTs have scope 'evaluation' and include jti."""
    private_key, public_key = keypair
    token = create_evaluator_jwt(private_key, "inst-1", "client-1", "proj-1", "task-1")
    payload = pyjwt.decode(token, public_key, algorithms=["EdDSA"])
    assert payload["project_id"] == "proj-1"
    assert payload["task_id"] == "task-1"
    assert payload["scope"] == "evaluation"
    assert "exp" in payload
    assert payload["exp"] - payload["iat"] == 86400
    assert "jti" in payload


def test_create_evaluator_jwt_is_eddsa(keypair):
    private_key, _ = keypair
    token = create_evaluator_jwt(private_key, "inst-1", "client-1", "proj-1", "task-1")
    header = pyjwt.get_unverified_header(token)
    assert header["alg"] == "EdDSA"


def test_evaluator_jwt_has_evaluation_scope(keypair):
    """v1.2.1: evaluator JWTs use scope 'evaluation', not 'task'."""
    private_key, public_key = keypair
    token = create_evaluator_jwt(
        private_key, instance_id="inst-1", client_id="client-1",
        project_id="proj-1", task_id="task-1",
    )
    payload = pyjwt.decode(token, public_key, algorithms=["EdDSA"])
    assert payload["scope"] == "evaluation"


def test_evaluator_jwt_has_jti(keypair):
    """v1.2.1: evaluator JWTs include a jti for single-use enforcement."""
    private_key, public_key = keypair
    token = create_evaluator_jwt(
        private_key, instance_id="inst-1", client_id="client-1",
        project_id="proj-1", task_id="task-1",
    )
    payload = pyjwt.decode(token, public_key, algorithms=["EdDSA"])
    assert "jti" in payload
    assert len(payload["jti"]) > 0


def test_evaluator_jwt_contains_all_13_claims(keypair):
    """v1.2.1 PRD §3.5: callback JWT must contain all 13 specified claims."""
    private_key, public_key = keypair
    primitive_ids = {
        "role_components": ["rc-1", "rc-2"],
        "desired_outcomes": ["do-1"],
        "trade_off_configs": ["tc-1"],
    }
    token = create_evaluator_jwt(
        private_key,
        instance_id="inst-1",
        client_id="mcp",
        project_id="proj-1",
        task_id="task-1",
        agent_composition_id="agent-comp-1",
        agent_content_hash="abc123",
        evaluator_agent_id="eval-agent-1",
        evaluator_content_hash="def456",
        task_agent_primitive_ids=primitive_ids,
    )
    payload = pyjwt.decode(token, public_key, algorithms=["EdDSA"])

    required_claims = [
        "jti", "client_id", "instance_id", "scope", "project_id",
        "task_id", "agent_composition_id", "agent_content_hash",
        "evaluator_agent_id", "evaluator_content_hash",
        "task_agent_primitive_ids", "iat", "exp",
    ]
    for claim in required_claims:
        assert claim in payload, f"Missing claim: {claim}"

    assert payload["scope"] == "evaluation"
    assert payload["agent_composition_id"] == "agent-comp-1"
    assert payload["agent_content_hash"] == "abc123"
    assert payload["evaluator_agent_id"] == "eval-agent-1"
    assert payload["evaluator_content_hash"] == "def456"
    assert payload["task_agent_primitive_ids"] == primitive_ids


def test_scope_grace_period_accepts_both_scopes():
    """During grace period, both 'task' and 'evaluation' scopes are valid."""
    from agency.auth.jwt import is_valid_evaluator_scope
    assert is_valid_evaluator_scope("evaluation") is True
    assert is_valid_evaluator_scope("task") is True
    assert is_valid_evaluator_scope("admin") is False
    assert is_valid_evaluator_scope("") is False


def test_verify_jwt_accepts_slight_clock_skew(keypair):
    """JWTs within 60s of expiry should still validate."""
    private_key, public_key = keypair
    exp = int(time.time()) - 30  # expired 30s ago, within 60s leeway
    token = create_jwt(private_key, "inst-1", "client-1", generate_uuid_v7(), exp=exp)
    payload = verify_jwt(token, public_key)
    assert payload["instance_id"] == "inst-1"
