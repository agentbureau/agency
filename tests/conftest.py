import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_llm():
    """Returns a mock LLM client. All tests use this — never real API calls."""
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="mocked LLM response")
    return llm


@pytest.fixture
def tmp_state_dir(tmp_path):
    """Temporary ~/.agency/ directory for each test."""
    state = tmp_path / ".agency"
    state.mkdir()
    (state / "keys").mkdir()
    return state


@pytest.fixture
def test_app(tmp_state_dir):
    """FastAPI test app with real temp DB, seeded primitives, auth tokens.

    Returns a dict with keys: app, client, db, state_dir, public_key, private_key, base_url.
    """
    import os
    import sqlite3
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from fastapi.responses import JSONResponse

    from agency.auth.keypair import generate_keypair, load_private_key, load_public_key
    from agency.db.migrations import run_migrations
    from agency.db.primitives import insert_primitive
    from agency.utils.ids import new_uuid

    # Generate keypair
    priv_path = str(tmp_state_dir / "keys" / "agency.ed25519.pem")
    pub_path = str(tmp_state_dir / "keys" / "agency.ed25519.pub.pem")
    generate_keypair(priv_path, pub_path)
    private_key = load_private_key(priv_path)
    public_key = load_public_key(pub_path)

    # Set up DB
    conn = sqlite3.connect(str(tmp_state_dir / "agency.db"), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    run_migrations(conn)

    instance_id = new_uuid()

    # Seed minimal primitives
    insert_primitive(conn, "role_components",
                     "You are a careful analyst who evaluates evidence before drawing conclusions.",
                     instance_id, name="test-role-component")
    insert_primitive(conn, "desired_outcomes",
                     "Produce structured output that distinguishes facts from inferences.",
                     instance_id, name="test-desired-outcome")
    insert_primitive(conn, "trade_off_configs",
                     "When speed and accuracy conflict, prefer accuracy.",
                     instance_id, name="test-trade-off-config")

    # Build app without lifespan — set state manually
    from agency.api.middleware import UNPROTECTED, check_token, MissingToken, TokenRevoked

    app = FastAPI(title="Agency-test")

    @app.middleware("http")
    async def jwt_middleware(request, call_next):
        if request.url.path in UNPROTECTED:
            return await call_next(request)
        pk = getattr(request.app.state, "public_key", None)
        db = request.app.state.db
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else None
        try:
            payload = check_token(token, pk, db)
        except MissingToken:
            return JSONResponse({"detail": "Missing or invalid Authorization header"}, status_code=401)
        except TokenRevoked:
            return JSONResponse({"detail": "Token has been revoked"}, status_code=401)
        except Exception as exc:
            return JSONResponse({"detail": str(exc)}, status_code=401)
        request.state.jwt_payload = payload
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "test"}

    from agency.api.routes import tasks, projects, primitives, evolution, status, triage
    app.include_router(tasks.router)
    app.include_router(projects.router)
    app.include_router(primitives.router)
    app.include_router(evolution.router)
    app.include_router(status.router)
    app.include_router(triage.router)

    app.state.db = conn
    app.state.state_dir = tmp_state_dir
    app.state.public_key = public_key
    app.state.private_key = private_key
    app.state.config = {"instance_id": instance_id, "server": {"host": "127.0.0.1", "port": 8000}}

    prev_env = os.environ.get("AGENCY_STATE_DIR")
    os.environ["AGENCY_STATE_DIR"] = str(tmp_state_dir)

    client = TestClient(app, raise_server_exceptions=True)

    yield {
        "app": app,
        "client": client,
        "db": conn,
        "state_dir": tmp_state_dir,
        "public_key": public_key,
        "private_key": private_key,
        "base_url": "http://testserver",
        "instance_id": instance_id,
    }

    conn.close()
    if prev_env is None:
        os.environ.pop("AGENCY_STATE_DIR", None)
    else:
        os.environ["AGENCY_STATE_DIR"] = prev_env


@pytest.fixture
def test_token(test_app):
    """Valid JWT bearer token for the test app."""
    from agency.auth.jwt import create_jwt
    from agency.utils.ids import new_uuid

    private_key = test_app["private_key"]
    instance_id = test_app["instance_id"]
    client_id = "test-client"
    jti = new_uuid()

    token = create_jwt(private_key, instance_id, client_id, jti)

    # Record in issued_tokens so middleware check passes
    test_app["db"].execute(
        "INSERT INTO issued_tokens (jti, client_id) VALUES (?, ?)",
        (jti, client_id),
    )
    test_app["db"].commit()
    return token


@pytest.fixture
def test_project_id(test_app, test_token):
    """Pre-created project ID for tests that need one."""
    from agency.db.projects import create_project

    project_id = create_project(
        test_app["db"],
        name="Test Project",
        client_id="test-client",
        description="Auto-created fixture project for tests.",
        admin_email=None,
    )
    return project_id
