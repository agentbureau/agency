import os
import sqlite3
import pytest
from click.testing import CliRunner
from agency.cli.primitives import primitives_command


@pytest.fixture
def runner_env(tmp_path):
    os.environ["AGENCY_STATE_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["AGENCY_STATE_DIR"]


def test_install_starter_primitives(runner_env):
    runner = CliRunner()
    result = runner.invoke(primitives_command, ["install"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "installed" in result.output

    db = sqlite3.connect(runner_env / "agency.db")
    count = db.execute(
        "SELECT COUNT(*) FROM primitives"
    ).fetchone()[0]
    assert count >= 50  # starter CSV has 113 primitives


def test_install_idempotent(runner_env):
    runner = CliRunner()
    runner.invoke(primitives_command, ["install"], catch_exceptions=False)
    result = runner.invoke(primitives_command, ["install"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "0 primitives installed" in result.output


def test_update_after_install(runner_env):
    runner = CliRunner()
    runner.invoke(primitives_command, ["install"], catch_exceptions=False)
    result = runner.invoke(primitives_command, ["update"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Unchanged:" in result.output


def test_list_primitives(runner_env):
    runner = CliRunner()
    runner.invoke(primitives_command, ["install"], catch_exceptions=False)
    result = runner.invoke(primitives_command, ["list"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "[q=" in result.output
