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
    private_key, public_key = keypair
    token = create_evaluator_jwt(private_key, "inst-1", "client-1", "proj-1", "task-1")
    payload = pyjwt.decode(token, public_key, algorithms=["EdDSA"])
    assert payload["project_id"] == "proj-1"
    assert payload["task_id"] == "task-1"
    assert "exp" in payload
    assert payload["exp"] - payload["iat"] == 86400
    assert "jti" not in payload  # evaluator JWTs have no jti


def test_create_evaluator_jwt_is_eddsa(keypair):
    private_key, _ = keypair
    token = create_evaluator_jwt(private_key, "inst-1", "client-1", "proj-1", "task-1")
    header = pyjwt.get_unverified_header(token)
    assert header["alg"] == "EdDSA"
