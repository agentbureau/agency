"""Unit tests for POST /triage endpoint (§4.7.5)."""
import sqlite3
import pytest
from fastapi.testclient import TestClient
from agency.api.app import create_app
from agency.auth.keypair import generate_keypair, load_private_key
from agency.auth.jwt import create_jwt
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive
from agency.engine.constants import TRIAGE_TOP_N, METAPRIMITIVE_SIMILARITY_THRESHOLD
from agency.utils.ids import generate_uuid_v7


def _setup_env(tmp_path, monkeypatch, seed_primitives=True):
    """Set up a complete Agency test environment."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))

    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    generate_keypair(
        str(keys_dir / "agency.ed25519.pem"),
        str(keys_dir / "agency.ed25519.pub.pem"),
    )

    db_path = tmp_path / "agency.db"
    conn = sqlite3.connect(db_path)
    run_migrations(conn)

    if seed_primitives:
        for desc in [
            "write clear and concise code",
            "review code for quality issues",
            "design system architecture",
            "test software thoroughly",
            "document technical decisions",
        ]:
            insert_primitive(conn, "role_components", description=desc, instance_id="inst-1")
        insert_primitive(conn, "desired_outcomes",
                         description="produce working, well-tested software",
                         instance_id="inst-1")
        insert_primitive(conn, "trade_off_configs",
                         description="quality and correctness over speed",
                         instance_id="inst-1")
    conn.close()


def _make_auth(tmp_path, app):
    """Create a valid auth header."""
    private_key = load_private_key(str(tmp_path / "keys" / "agency.ed25519.pem"))
    jti = generate_uuid_v7()
    app.state.db.execute(
        "INSERT INTO issued_tokens (jti, client_id) VALUES (?, ?)",
        (jti, "test-client"),
    )
    app.state.db.commit()
    token = create_jwt(private_key, "test-inst", "test-client", jti)
    return {"Authorization": f"Bearer {token}"}


def test_triage_returns_matched_primitives(tmp_path, monkeypatch):
    """Triage returns response with matched_primitives, recommendation, reasoning."""
    _setup_env(tmp_path, monkeypatch)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)
        r = c.post("/triage", json={"description": "write a sorting algorithm"}, headers=auth)
        assert r.status_code == 200
        body = r.json()
        assert "matched_primitives" in body
        assert "recommendation" in body
        assert "reasoning" in body
        assert "task_type" in body
        assert body["task_type"] in (
            "research", "build", "review", "analyse", "write",
            "design", "debug", "plan", "audit", "evaluate", "advise", "synthesise",
        )
        assert isinstance(body["matched_primitives"], list)
        for p in body["matched_primitives"]:
            assert "name" in p
            assert "type" in p
            assert "similarity" in p
            assert p["type"] in ("role_component", "desired_outcome", "trade_off_config")


def test_triage_recommendation_compose_when_strong_match(tmp_path, monkeypatch):
    """When a primitive has high similarity, recommendation should be 'compose'."""
    _setup_env(tmp_path, monkeypatch)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)
        # Use a description very close to a seeded primitive
        r = c.post("/triage", json={"description": "write clear and concise code"}, headers=auth)
        assert r.status_code == 200
        body = r.json()
        # The exact same text should produce a very high similarity match
        assert body["recommendation"] in ("compose", "compose_with_advisory")
        assert "Recommendation:" in body["reasoning"]


def test_triage_recommendation_skip_when_no_strong_match(tmp_path, monkeypatch):
    """When no primitive exceeds threshold, recommendation may be compose_unlikely_to_help."""
    _setup_env(tmp_path, monkeypatch)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)
        # Use a description totally unrelated to seeded primitives
        r = c.post("/triage", json={
            "description": "bake a chocolate soufflé with vanilla bean extraction"
        }, headers=auth)
        assert r.status_code == 200
        body = r.json()
        assert body["recommendation"] in (
            "compose", "compose_with_advisory", "compose_unlikely_to_help",
        )
        # Verify three-signal response shape
        assert "signals" in body
        assert "fitness_estimate" in body


def test_triage_empty_description_returns_422(tmp_path, monkeypatch):
    """Empty description string returns 422."""
    _setup_env(tmp_path, monkeypatch)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)
        r = c.post("/triage", json={"description": ""}, headers=auth)
        assert r.status_code == 422
        body = r.json()
        assert body["detail"]["code"] == "triage_missing_description"

        # Whitespace-only should also fail
        r = c.post("/triage", json={"description": "   "}, headers=auth)
        assert r.status_code == 422


def test_triage_empty_store_returns_warning(tmp_path, monkeypatch):
    """When no primitives are installed, response includes a warning."""
    _setup_env(tmp_path, monkeypatch, seed_primitives=False)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)
        r = c.post("/triage", json={"description": "write some code"}, headers=auth)
        assert r.status_code == 200
        body = r.json()
        assert body["warning"] is not None
        assert "No primitives installed" in body["warning"]
        assert body["recommendation"] == "compose_unlikely_to_help"
        assert body["matched_primitives"] == []


def test_triage_is_stateless(tmp_path, monkeypatch):
    """Triage must not create any task record in the database."""
    _setup_env(tmp_path, monkeypatch)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)

        # Count tasks before
        before = app.state.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]

        r = c.post("/triage", json={"description": "write a sorting algorithm"}, headers=auth)
        assert r.status_code == 200

        # Count tasks after — should be identical
        after = app.state.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        assert after == before, "Triage should not create task records"


def test_triage_max_results_capped(tmp_path, monkeypatch):
    """Even with many primitives, at most TRIAGE_TOP_N are returned."""
    _setup_env(tmp_path, monkeypatch, seed_primitives=False)

    # Seed more than TRIAGE_TOP_N primitives across tables
    db_path = tmp_path / "agency.db"
    conn = sqlite3.connect(db_path)
    for i in range(TRIAGE_TOP_N + 5):
        insert_primitive(conn, "role_components",
                         description=f"programming skill variant {i}",
                         instance_id="inst-1")
    for i in range(TRIAGE_TOP_N + 3):
        insert_primitive(conn, "desired_outcomes",
                         description=f"outcome variant {i}",
                         instance_id="inst-1")
    conn.close()

    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)
        r = c.post("/triage", json={"description": "programming skill variant 1"}, headers=auth)
        assert r.status_code == 200
        body = r.json()
        assert len(body["matched_primitives"]) <= TRIAGE_TOP_N
