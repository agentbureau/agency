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
    assert "Installed" in result.output

    db = sqlite3.connect(runner_env / "agency.db")
    count = db.execute("SELECT COUNT(*) FROM role_components").fetchone()[0]
    assert count >= 8  # starter set has 8 role components


def test_install_extended_primitives(runner_env):
    runner = CliRunner()
    result = runner.invoke(primitives_command, ["install", "--extended"],
                           catch_exceptions=False)
    assert result.exit_code == 0
    db = sqlite3.connect(runner_env / "agency.db")
    count = db.execute("SELECT COUNT(*) FROM role_components").fetchone()[0]
    assert count >= 12  # starter (8) + extended (4)


def test_install_idempotent(runner_env):
    runner = CliRunner()
    runner.invoke(primitives_command, ["install"], catch_exceptions=False)
    result = runner.invoke(primitives_command, ["install"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "already present" in result.output


def test_update_adds_only_new(runner_env):
    runner = CliRunner()
    runner.invoke(primitives_command, ["install"], catch_exceptions=False)
    result = runner.invoke(primitives_command, ["update"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "already present" in result.output
