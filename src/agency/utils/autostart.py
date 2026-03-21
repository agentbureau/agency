"""MCP auto-start utilities for zero-terminal Agency operation."""
import pathlib
import shutil
import subprocess
import sys
import time

import httpx


def _resolve_agency_binary() -> str | None:
    """Resolve the absolute path to the agency binary.

    Resolution order:
    1. Sibling of current Python executable (same venv/pipx env)
    2. ~/.local/bin/agency (pipx default)
    3. {sys.prefix}/bin/agency (current venv)
    4. shutil.which fallback (PATH search)
    """
    # 1. Same installation as the running process
    exe_dir = pathlib.Path(sys.executable).resolve().parent
    sibling = exe_dir / "agency"
    if sibling.is_file() and sibling.stat().st_mode & 0o111:
        return str(sibling)

    # 2. pipx default location
    pipx_path = pathlib.Path.home() / ".local" / "bin" / "agency"
    if pipx_path.is_file() and pipx_path.stat().st_mode & 0o111:
        return str(pipx_path.resolve())

    # 3. Current venv
    venv_path = pathlib.Path(sys.prefix) / "bin" / "agency"
    if venv_path.is_file() and venv_path.stat().st_mode & 0o111:
        return str(venv_path.resolve())

    # 4. PATH fallback
    found = shutil.which("agency")
    if found:
        return str(pathlib.Path(found).resolve())

    return None


def _poll_health(
    host: str = "127.0.0.1",
    port: int = 8000,
    timeout: float = 30.0,
    interval: float = 0.5,
) -> bool:
    """Poll the health endpoint until it responds or timeout.

    Returns True if healthy, False if timed out.
    """
    url = f"http://{host}:{port}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        time.sleep(interval)
    return False


def auto_start_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    timeout: float = 30.0,
) -> subprocess.Popen | None:
    """Start agency serve if not already running.

    Returns the Popen object if started, None if already running.
    Raises RuntimeError if cannot start.
    """
    # Check if already running
    try:
        r = httpx.get(f"http://{host}:{port}/health", timeout=2.0)
        if r.status_code == 200:
            return None  # Already running
    except (httpx.ConnectError, httpx.TimeoutException):
        pass

    # Find binary
    binary = _resolve_agency_binary()
    if binary is None:
        raise RuntimeError(
            "agency binary not found on PATH. "
            "Install with: pipx install --python python3.13 agency-engine"
        )

    # Spawn server
    proc = subprocess.Popen(
        [binary, "serve", "--host", host, "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for health
    if not _poll_health(host, port, timeout):
        proc.terminate()
        raise RuntimeError(
            f"Agency server did not become healthy within {timeout}s. "
            f"Check logs or run 'agency serve' manually."
        )

    return proc
