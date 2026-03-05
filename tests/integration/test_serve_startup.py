import os
import pytest
from fastapi.testclient import TestClient


def test_serve_startup_runs_migrations(tmp_path):
    """App startup runs migrations and /health returns ok."""
    os.environ["AGENCY_STATE_DIR"] = str(tmp_path)
    try:
        from agency.api.app import create_app
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
        assert (tmp_path / "agency.db").exists()
    finally:
        del os.environ["AGENCY_STATE_DIR"]
