import sqlite3
import pytest
from agency.auth.keypair import generate_keypair, load_private_key, load_public_key
from agency.auth.jwt import create_jwt, create_evaluator_jwt
from agency.utils.ids import generate_uuid_v7


@pytest.fixture
def keypair(tmp_path):
    priv = str(tmp_path / "key.pem")
    pub = str(tmp_path / "key.pub.pem")
    generate_keypair(priv, pub)
    return load_private_key(priv), load_public_key(pub)


@pytest.fixture
def db_with_token(tmp_path):
    from agency.db.migrations import run_migrations
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    run_migrations(conn)
    jti = generate_uuid_v7()
    conn.execute(
        "INSERT INTO issued_tokens (jti, client_id) VALUES (?, ?)",
        (jti, "mcp"),
    )
    conn.commit()
    return conn, jti


def test_valid_token_passes_middleware(keypair, db_with_token):
    private_key, public_key = keypair
    conn, jti = db_with_token
    token = create_jwt(private_key, "inst-1", "mcp", jti)
    from agency.api.middleware import check_token
    result = check_token(token, public_key, conn)
    assert result["client_id"] == "mcp"


def test_revoked_token_rejected(keypair, db_with_token):
    private_key, public_key = keypair
    conn, jti = db_with_token
    conn.execute("UPDATE issued_tokens SET revoked = 1 WHERE jti = ?", (jti,))
    conn.commit()
    token = create_jwt(private_key, "inst-1", "mcp", jti)
    from agency.api.middleware import check_token, TokenRevoked
    with pytest.raises(TokenRevoked):
        check_token(token, public_key, conn)


def test_evaluator_jwt_with_jti_passes_revocation_check(keypair, db_with_token):
    """v1.2.1: evaluator JWTs now include jti for single-use enforcement."""
    private_key, public_key = keypair
    conn, _ = db_with_token
    token = create_evaluator_jwt(private_key, "inst-1", "client-1", "proj-1", "task-1")
    from agency.api.middleware import check_token
    payload = check_token(token, public_key, conn)
    assert payload["task_id"] == "task-1"
    assert "jti" in payload  # v1.2.1: evaluator JWTs have jti


def test_missing_auth_header_raises(keypair, db_with_token):
    _, public_key = keypair
    conn, _ = db_with_token
    from agency.api.middleware import check_token, MissingToken
    with pytest.raises(MissingToken):
        check_token(None, public_key, conn)
