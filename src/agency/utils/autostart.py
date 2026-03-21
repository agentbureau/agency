"""MCP auto-start utilities for zero-terminal Agency operation."""
import shutil
import subprocess
import time

import httpx


def _resolve_agency_binary() -> str | None:
    """Find the agency binary on PATH. Returns path or None."""
    return shutil.which("agency")


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
