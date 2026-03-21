"""agency skills install — install bundled Claude Code skills."""
import hashlib
import os
import shutil

import click


BUNDLED_SKILLS = [
    "agency-primitive-extraction",
    "agency-getting-started",
    "agency-composition-config",
]


def _bundled_skill_path(skill_name: str) -> str:
    """Return the path to the bundled skill file in the installed package."""
    import agency.skills
    skills_dir = os.path.dirname(agency.skills.__file__)
    return os.path.join(skills_dir, skill_name, "SKILL.md")


def _skill_content_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _install_skill(skill_name: str, claude_skills_dir: str) -> str:
    """Install a bundled skill. Returns 'installed' or 'already_current'."""
    bundled = _bundled_skill_path(skill_name)
    dest_dir = os.path.join(claude_skills_dir, skill_name)
    dest = os.path.join(dest_dir, "SKILL.md")

    os.makedirs(dest_dir, exist_ok=True)

    if os.path.exists(dest) and _skill_content_hash(dest) == _skill_content_hash(bundled):
        return "already_current"

    shutil.copy2(bundled, dest)
    return "installed"


@click.command("install")
def skills_install_command():
    """Install (or update) bundled Claude Code skills into ~/.claude/skills/."""
    claude_dir = os.path.join(os.path.expanduser("~"), ".claude")
    if not os.path.isdir(claude_dir):
        click.echo("Error: ~/.claude/ not found. Is Claude Code installed?")
        raise SystemExit(1)

    skills_dir = os.path.join(claude_dir, "skills")
    os.makedirs(skills_dir, exist_ok=True)

    for skill_name in BUNDLED_SKILLS:
        try:
            status = _install_skill(skill_name, skills_dir)
            if status == "already_current":
                click.echo(f"  {skill_name:<50} Already current.")
            else:
                click.echo(f"  {skill_name:<50} Installed")
        except (IOError, OSError) as e:
            click.echo(f"Error: Could not write to {skills_dir} ({e}).")
            raise SystemExit(1)
