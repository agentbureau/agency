import pytest
from fastapi.testclient import TestClient
from agency.api.app import create_app


def test_create_project_persists_across_app_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENCY_JWT_SECRET", "")
    app1 = create_app()
    with TestClient(app1) as c1:
        r = c1.post("/projects", json={"name": "myproject"})
        assert r.status_code == 201
        pid = r.json()["project_id"]

    app2 = create_app()
    with TestClient(app2) as c2:
        r = c2.get(f"/projects/{pid}")
        assert r.status_code == 200
        assert r.json()["name"] == "myproject"


def test_get_project_404_if_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENCY_JWT_SECRET", "")
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/projects/nonexistent")
        assert r.status_code == 404
