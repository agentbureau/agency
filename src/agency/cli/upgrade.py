"""
Task 36: agency upgrade — check GitHub releases, backup state, pip install.
"""
import os
import shutil
import subprocess
import sys
import click
import httpx
from pathlib import Path

from agency.constants import GITHUB_ORG, GITHUB_REPO


def _state_dir() -> Path:
    return Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))


def _get_latest_release(repo: str) -> dict | None:
    try:
        resp = httpx.get(
            f"https://api.github.com/repos/{repo}/releases/latest",
            timeout=10.0,
            headers={"Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _backup_state(state_dir: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for item in state_dir.iterdir():
        dest = backup_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


@click.command("upgrade")
@click.option("--repo", default=f"{GITHUB_ORG}/{GITHUB_REPO}",
              help="GitHub repo (owner/name) to check for releases")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation")
@click.option("--dry-run", is_flag=True, default=False,
              help="Check for updates but do not install")
def upgrade_command(repo: str, yes: bool, dry_run: bool):
    """Upgrade Agency to the latest version from GitHub."""
    click.echo(f"Checking latest release from github.com/{repo}...")

    release = _get_latest_release(repo)
    if not release:
        click.echo("Could not reach GitHub releases API. Check your connection.", err=True)
        raise SystemExit(1)

    tag = release.get("tag_name", "unknown")
    click.echo(f"Latest release: {tag}")

    if dry_run:
        click.echo("(dry-run) Would install agency-engine from this release.")
        return

    if not yes:
        click.confirm(f"Install {tag}?", default=True, abort=True)

    state_dir = _state_dir()
    backup_dir = state_dir.parent / f".agency-backup-{tag}"
    if state_dir.exists():
        click.echo(f"Backing up state to {backup_dir}...")
        _backup_state(state_dir, backup_dir)
        click.echo("✓ Backup complete")

    click.echo("Installing latest package...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "agency-engine"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        click.echo(f"pip install failed:\n{result.stderr}", err=True)
        click.echo(f"Your state backup is at: {backup_dir}")
        raise SystemExit(1)

    click.echo(f"✓ Upgraded to {tag}")
    click.echo("Restart `agency serve` to apply the upgrade.")
