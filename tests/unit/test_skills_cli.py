import os
from click.testing import CliRunner
from agency.cli.skills import skills_install_command


def test_skills_install_copies_skill_file(tmp_path, monkeypatch):
    """agency skills install copies bundled skill to ~/.claude/skills/."""
    fake_claude_dir = tmp_path / ".claude"
    fake_claude_dir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    runner = CliRunner()
    result = runner.invoke(skills_install_command)

    assert result.exit_code == 0
    skill_path = fake_claude_dir / "skills" / "agency-primitive-extraction" / "SKILL.md"
    assert skill_path.exists()
    assert "agency-primitive-extraction" in result.output


def test_skills_install_errors_when_claude_not_installed(tmp_path, monkeypatch):
    """Prints error when ~/.claude/ does not exist."""
    monkeypatch.setenv("HOME", str(tmp_path))  # no .claude dir
    runner = CliRunner()
    result = runner.invoke(skills_install_command)
    assert result.exit_code != 0
    assert "~/.claude/" in result.output or ".claude" in result.output


def test_skills_install_is_idempotent(tmp_path, monkeypatch):
    """Running skills install twice: second run reports Already current."""
    fake_claude_dir = tmp_path / ".claude"
    fake_claude_dir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    runner = CliRunner()
    result1 = runner.invoke(skills_install_command)
    result2 = runner.invoke(skills_install_command)
    assert result1.exit_code == 0
    assert result2.exit_code == 0
    assert "Already current" in result2.output
