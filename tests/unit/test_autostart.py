"""Tests for MCP auto-start utilities."""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from agency.utils.autostart import (
    _poll_health,
    _resolve_agency_binary,
    auto_start_server,
)


def test_resolve_agency_binary_finds_or_none():
    """Verify _resolve_agency_binary returns a string path or None.

    Resolution order: sys.executable sibling → ~/.local/bin → sys.prefix/bin → shutil.which.
    We test that it returns a path when agency is installed (current env),
    and that it returns a string (not None) since we're running in the agency venv.
    """
    result = _resolve_agency_binary()
    # We're running inside the agency venv, so it should find the binary
    assert result is not None
    assert isinstance(result, str)
    assert result.endswith("/agency")


def test_poll_health_returns_true_when_healthy():
    """Mock httpx.get to return 200 — poll should return True immediately."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("agency.utils.autostart.httpx.get", return_value=mock_response):
        assert _poll_health(timeout=2.0, interval=0.1) is True


def test_poll_health_returns_false_on_timeout():
    """Mock httpx.get to always raise ConnectError — poll should time out."""
    with patch(
        "agency.utils.autostart.httpx.get",
        side_effect=httpx.ConnectError("refused"),
    ):
        assert _poll_health(timeout=0.3, interval=0.1) is False


def test_auto_start_returns_none_when_already_running():
    """If health check returns 200, server is already up — return None."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("agency.utils.autostart.httpx.get", return_value=mock_response):
        result = auto_start_server(timeout=1.0)
        assert result is None


def test_auto_start_raises_when_no_binary():
    """If no binary can be found at any resolution step, raise RuntimeError."""
    with patch(
        "agency.utils.autostart.httpx.get",
        side_effect=httpx.ConnectError("refused"),
    ):
        with patch(
            "agency.utils.autostart._resolve_agency_binary",
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="agency binary not found"):
                auto_start_server(timeout=1.0)
