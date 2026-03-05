import os
import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from agency.cli.upgrade import upgrade_command


@pytest.fixture
def runner_env(tmp_path):
    os.environ["AGENCY_STATE_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["AGENCY_STATE_DIR"]


def _mock_release(tag: str = "v1.1.0") -> dict:
    return {"tag_name": tag, "name": f"Agency {tag}"}


def test_upgrade_dry_run(runner_env):
    runner = CliRunner()
    with patch("agency.cli.upgrade._get_latest_release", return_value=_mock_release()):
        result = runner.invoke(upgrade_command, ["--dry-run", "--yes"],
                               catch_exceptions=False)
    assert result.exit_code == 0
    assert "v1.1.0" in result.output
    assert "dry-run" in result.output


def test_upgrade_no_release_exits_nonzero(runner_env):
    runner = CliRunner()
    with patch("agency.cli.upgrade._get_latest_release", return_value=None):
        result = runner.invoke(upgrade_command, ["--dry-run"])
    assert result.exit_code != 0


def test_upgrade_creates_backup(runner_env):
    (runner_env / "agency.toml").write_text("[test]\n")
    runner = CliRunner()

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with patch("agency.cli.upgrade._get_latest_release", return_value=_mock_release("v1.2.0")):
        with patch("subprocess.run", return_value=mock_proc):
            result = runner.invoke(upgrade_command, ["--yes"], catch_exceptions=False)

    assert result.exit_code == 0
    backup_dir = runner_env.parent / ".agency-backup-v1.2.0"
    assert backup_dir.exists()
    assert (backup_dir / "agency.toml").exists()


def test_upgrade_pip_failure_reports_backup(runner_env):
    (runner_env / "agency.toml").write_text("[test]\n")
    runner = CliRunner()

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "some pip error"
    with patch("agency.cli.upgrade._get_latest_release", return_value=_mock_release("v1.2.0")):
        with patch("subprocess.run", return_value=mock_proc):
            result = runner.invoke(upgrade_command, ["--yes"])

    assert result.exit_code != 0
    assert "backup" in result.output.lower()
