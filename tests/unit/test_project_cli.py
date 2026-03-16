import json
import sqlite3
import os
import re
import tomllib
from unittest.mock import patch, MagicMock

from click.testing import CliRunner
from agency.db.migrations import run_migrations
from agency.cli.project import (
    project_create_command,
    project_list_command,
    project_pin_command,
    run_project_create_wizard,
)


def _setup_db_and_toml(tmp_path, toml_overrides=None):
    """Helper: create migrated DB and agency.toml, return (db_path, toml_path)."""
    db_path = str(tmp_path / "agency.db")
    conn = sqlite3.connect(db_path)
    run_migrations(conn)
    conn.close()

    toml_content = (
        'instance_id = "inst-1"\n'
        '[server]\nhost = "127.0.0.1"\nport = 8000\n'
        '[notifications]\ncontact_email = "inst@example.com"\n'
        'oversight_preference = "discretion"\nerror_notification_timeout = 1800\n'
        '[output]\nattribution = true\n'
    )
    if toml_overrides:
        toml_content = toml_overrides

    toml_path = str(tmp_path / "agency.toml")
    with open(toml_path, "w") as f:
        f.write(toml_content)

    return db_path, toml_path


def test_project_create_minimal(tmp_path, monkeypatch):
    """agency project create creates a project row with minimal input."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    runner = CliRunner()
    # Input: project name, then enter for all defaults, n for LLM override, n for default
    result = runner.invoke(project_create_command, [], input="My Test Project\n\n\n\n\nn\nn\n")

    assert result.exit_code == 0, result.output
    assert "My Test Project" in result.output
    assert re.search(r"[0-9a-f-]{36}", result.output) is not None


def test_project_create_sets_default_in_toml(tmp_path, monkeypatch):
    """agency project create with y for default updates agency.toml."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    runner = CliRunner()
    # Project name, defaults for all fields, n for LLM override, y for set as default
    result = runner.invoke(project_create_command, [], input="My Project\n\n\n\n\nn\ny\n")
    assert result.exit_code == 0, result.output

    with open(str(tmp_path / "agency.toml"), "rb") as f:
        cfg = tomllib.load(f)
    assert "project" in cfg
    assert "default_id" in cfg["project"]


def test_project_create_stores_null_for_inherited_fields(tmp_path, monkeypatch):
    """Pressing enter (accepting defaults) stores NULL in DB, not the instance value."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(project_create_command, [], input="Inherit Project\n\n\n\n\nn\nn\n")
    assert result.exit_code == 0, result.output

    # Extract UUID from output
    match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", result.output)
    assert match, f"No UUID found in output: {result.output}"
    project_id = match.group(1)

    conn = sqlite3.connect(str(tmp_path / "agency.db"))
    row = conn.execute("SELECT contact_email, oversight_preference, error_notification_timeout, attribution FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    assert row is not None
    # All should be None (inherited)
    assert row[0] is None  # contact_email
    assert row[1] is None  # oversight_preference
    assert row[2] is None  # error_notification_timeout
    assert row[3] is None  # attribution


def test_project_create_stores_overridden_values(tmp_path, monkeypatch):
    """Entering explicit values stores them in the DB."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    runner = CliRunner()
    # Provide explicit values for all fields
    result = runner.invoke(
        project_create_command, [],
        input="Custom Project\ncustom@example.com\nalways\n3600\nfalse\nn\nn\n",
    )
    assert result.exit_code == 0, result.output

    match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", result.output)
    assert match
    project_id = match.group(1)

    conn = sqlite3.connect(str(tmp_path / "agency.db"))
    row = conn.execute("SELECT contact_email, oversight_preference, error_notification_timeout, attribution FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    assert row[0] == "custom@example.com"
    assert row[1] == "always"
    assert row[2] == 3600
    assert row[3] == 0  # false -> 0


def test_project_create_with_llm_override(tmp_path, monkeypatch):
    """LLM override section stores provider and model."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    runner = CliRunner()
    # y for LLM override, provide provider and model, n for default
    result = runner.invoke(
        project_create_command, [],
        input="LLM Project\n\n\n\n\ny\nopenai\ngpt-4\nsk-key123\nn\n",
    )
    assert result.exit_code == 0, result.output

    match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", result.output)
    assert match
    project_id = match.group(1)

    conn = sqlite3.connect(str(tmp_path / "agency.db"))
    row = conn.execute("SELECT llm_provider, llm_model, llm_api_key FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    assert row[0] == "openai"
    assert row[1] == "gpt-4"
    assert row[2] == "sk-key123"


def test_run_project_create_wizard_reusable(tmp_path):
    """run_project_create_wizard is callable directly (for use by agency init)."""
    db_path, toml_path = _setup_db_and_toml(tmp_path)
    conn = sqlite3.connect(db_path)

    runner = CliRunner()
    # We test the reusable function via Click's CliRunner for input handling
    @__import__("click").command()
    def _wrapper():
        project_id = run_project_create_wizard(str(tmp_path), conn, toml_path)
        __import__("click").echo(f"created:{project_id}")

    result = runner.invoke(_wrapper, [], input="Wizard Project\n\n\n\n\nn\nn\n")
    assert result.exit_code == 0, result.output
    assert "created:" in result.output

    # Verify row exists
    row = conn.execute("SELECT name FROM projects WHERE name = 'Wizard Project'").fetchone()
    conn.close()
    assert row is not None


# ---------------------------------------------------------------------------
# project list
# ---------------------------------------------------------------------------


def _mock_httpx_get(url, **kwargs):
    """Return a mock response for GET /projects."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "projects": [
            {"id": "aaa-bbb", "name": "Alpha", "created_at": "2026-01-01T00:00:00"},
            {"id": "ccc-ddd", "name": "Beta", "created_at": "2026-01-02T00:00:00"},
        ],
        "default_project_id": "aaa-bbb",
    }
    return resp


def test_project_list_table_output(tmp_path, monkeypatch):
    """agency project list prints table format with * marker for default."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    # Write a token file
    token_path = str(tmp_path / "token")
    with open(token_path, "w") as f:
        f.write("test-token")
    monkeypatch.setenv("AGENCY_TOKEN_FILE", token_path)

    runner = CliRunner()
    with patch("agency.cli.project.httpx.get", side_effect=_mock_httpx_get):
        result = runner.invoke(project_list_command, [])

    assert result.exit_code == 0, result.output
    assert "Alpha" in result.output
    assert "Beta" in result.output
    assert "*" in result.output  # default marker


def test_project_list_json_output(tmp_path, monkeypatch):
    """agency project list --format json returns valid JSON."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    token_path = str(tmp_path / "token")
    with open(token_path, "w") as f:
        f.write("test-token")
    monkeypatch.setenv("AGENCY_TOKEN_FILE", token_path)

    runner = CliRunner()
    with patch("agency.cli.project.httpx.get", side_effect=_mock_httpx_get):
        result = runner.invoke(project_list_command, ["--format", "json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "projects" in data
    assert len(data["projects"]) == 2
    assert data["projects"][0]["is_default"] is True


def test_project_list_empty(tmp_path, monkeypatch):
    """agency project list with no projects prints message."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    token_path = str(tmp_path / "token")
    with open(token_path, "w") as f:
        f.write("test-token")
    monkeypatch.setenv("AGENCY_TOKEN_FILE", token_path)

    def _empty_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"projects": [], "default_project_id": None}
        return resp

    runner = CliRunner()
    with patch("agency.cli.project.httpx.get", side_effect=_empty_get):
        result = runner.invoke(project_list_command, [])

    assert result.exit_code == 0, result.output
    assert "No projects found." in result.output


def test_project_list_server_unreachable(tmp_path, monkeypatch):
    """agency project list prints error when server is down."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    token_path = str(tmp_path / "token")
    with open(token_path, "w") as f:
        f.write("test-token")
    monkeypatch.setenv("AGENCY_TOKEN_FILE", token_path)

    import httpx as _httpx

    runner = CliRunner()
    with patch("agency.cli.project.httpx.get", side_effect=_httpx.ConnectError("refused")):
        result = runner.invoke(project_list_command, [])

    assert result.exit_code == 1
    assert "Cannot reach Agency server" in result.output


# ---------------------------------------------------------------------------
# project create (non-interactive via --name)
# ---------------------------------------------------------------------------


def test_project_create_noninteractive(tmp_path, monkeypatch):
    """agency project create --name calls POST /projects API."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    token_path = str(tmp_path / "token")
    with open(token_path, "w") as f:
        f.write("test-token")
    monkeypatch.setenv("AGENCY_TOKEN_FILE", token_path)

    def _mock_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {
            "id": "new-uuid-123",
            "name": "CLI Test Project",
            "created_at": "2026-01-01T00:00:00",
        }
        return resp

    runner = CliRunner()
    with patch("agency.cli.project.httpx.post", side_effect=_mock_post):
        result = runner.invoke(project_create_command, ["--name", "CLI Test Project"])

    assert result.exit_code == 0, result.output
    assert "CLI Test Project" in result.output
    assert "new-uuid-123" in result.output


def test_project_create_noninteractive_json(tmp_path, monkeypatch):
    """agency project create --name --format json returns JSON."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    token_path = str(tmp_path / "token")
    with open(token_path, "w") as f:
        f.write("test-token")
    monkeypatch.setenv("AGENCY_TOKEN_FILE", token_path)

    def _mock_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {
            "id": "new-uuid-456",
            "name": "JSON Project",
            "created_at": "2026-01-01T00:00:00",
        }
        return resp

    runner = CliRunner()
    with patch("agency.cli.project.httpx.post", side_effect=_mock_post):
        result = runner.invoke(project_create_command, [
            "--name", "JSON Project", "--format", "json",
        ])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["id"] == "new-uuid-456"


def test_project_create_noninteractive_duplicate(tmp_path, monkeypatch):
    """Non-interactive create shows error on duplicate name."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    token_path = str(tmp_path / "token")
    with open(token_path, "w") as f:
        f.write("test-token")
    monkeypatch.setenv("AGENCY_TOKEN_FILE", token_path)

    def _mock_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 409
        resp.text = '{"error": "duplicate_name", "message": "A project named \\"Dup\\" already exists."}'
        return resp

    runner = CliRunner()
    with patch("agency.cli.project.httpx.post", side_effect=_mock_post):
        result = runner.invoke(project_create_command, ["--name", "Dup"])

    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# project pin
# ---------------------------------------------------------------------------


def test_project_pin_writes_file(tmp_path, monkeypatch):
    """agency project pin --project-id writes .agency-project file."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    token_path = str(tmp_path / "token")
    with open(token_path, "w") as f:
        f.write("test-token")
    monkeypatch.setenv("AGENCY_TOKEN_FILE", token_path)

    # Mock the API call that validates the project exists
    def _mock_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "id": "pin-uuid-789",
            "name": "Pinned Project",
        }
        return resp

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        with patch("agency.cli.project.httpx.get", side_effect=_mock_get):
            result = runner.invoke(project_pin_command, ["--project-id", "pin-uuid-789"])

        assert result.exit_code == 0, result.output
        pin_file = os.path.join(td, ".agency-project")
        assert os.path.exists(pin_file)
        with open(pin_file) as f:
            assert f.read().strip() == "pin-uuid-789"


def test_project_pin_invalid_project(tmp_path, monkeypatch):
    """agency project pin with non-existent project shows error."""
    _setup_db_and_toml(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    token_path = str(tmp_path / "token")
    with open(token_path, "w") as f:
        f.write("test-token")
    monkeypatch.setenv("AGENCY_TOKEN_FILE", token_path)

    def _mock_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 404
        resp.text = "Not found"
        return resp

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        with patch("agency.cli.project.httpx.get", side_effect=_mock_get):
            result = runner.invoke(project_pin_command, ["--project-id", "nonexistent"])

    assert result.exit_code == 1
