"""Tests for agency.cli.wizard_ui — three-layer typographic system."""
import io
import sys
from unittest.mock import patch

import pytest

from agency.cli.wizard_ui import (
    status,
    helper,
    SETTING_HELP,
    _is_tty,
)


class TestStatus:
    """Tests for the status() function."""

    def test_status_outputs_checkmark(self, capsys):
        """status(msg, success=True) includes a checkmark character."""
        with patch("agency.cli.wizard_ui._is_tty", return_value=True):
            status("Test message")
        captured = capsys.readouterr()
        assert "\u2713" in captured.out  # ✓

    def test_status_failure_outputs_cross(self, capsys):
        """status(msg, success=False) includes a cross character."""
        with patch("agency.cli.wizard_ui._is_tty", return_value=True):
            status("Error message", success=False)
        captured = capsys.readouterr()
        assert "\u2717" in captured.out  # ✗

    def test_status_non_tty_success(self, capsys):
        """Non-TTY mode uses [ok] instead of checkmark."""
        with patch("agency.cli.wizard_ui._is_tty", return_value=False):
            status("Test message")
        captured = capsys.readouterr()
        assert "[ok]" in captured.out
        assert "\u2713" not in captured.out

    def test_status_non_tty_failure(self, capsys):
        """Non-TTY mode uses [FAIL] instead of cross."""
        with patch("agency.cli.wizard_ui._is_tty", return_value=False):
            status("Error message", success=False)
        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out
        assert "\u2717" not in captured.out


class TestHelper:
    """Tests for the helper() function."""

    def test_helper_indents_four_spaces(self, capsys):
        """helper() indents each line by 4 spaces."""
        with patch("agency.cli.wizard_ui._is_tty", return_value=False):
            helper("Line one\nLine two")
        captured = capsys.readouterr()
        for line in captured.out.splitlines():
            if line:  # skip empty lines
                assert line.startswith("    "), f"Line not indented with 4 spaces: {line!r}"

    def test_helper_multiline(self, capsys):
        """helper() handles multi-line strings, outputting one line per input line."""
        with patch("agency.cli.wizard_ui._is_tty", return_value=False):
            helper("First\nSecond\nThird")
        captured = capsys.readouterr()
        lines = captured.out.strip().splitlines()
        assert len(lines) == 3


class TestSettingHelp:
    """Tests for the SETTING_HELP dictionary."""

    def test_setting_help_has_all_keys(self):
        """SETTING_HELP contains entries for all expected wizard settings."""
        expected_keys = {
            "instance_credentials",
            "server_settings",
            "oversight_preference",
            "contact_email",
            "attribution",
            "error_notification_timeout",
            "llm_backend",
            "register_mcp",
            "database_init",
            "embedding_model",
            "integration_tokens",
            "project_name",
            "default_project",
            "smtp",
        }
        assert expected_keys.issubset(set(SETTING_HELP.keys())), (
            f"Missing keys: {expected_keys - set(SETTING_HELP.keys())}"
        )

    def test_setting_help_values_are_strings(self):
        """All SETTING_HELP values are non-empty strings."""
        for key, value in SETTING_HELP.items():
            assert isinstance(value, str), f"SETTING_HELP[{key!r}] is not a string"
            assert len(value) > 0, f"SETTING_HELP[{key!r}] is empty"


class TestNonTtyNoAnsi:
    """Tests that non-TTY mode produces no ANSI escape sequences."""

    def test_non_tty_no_ansi_codes(self, capsys):
        """When isatty=False, status() and helper() output contains no escape sequences."""
        with patch("agency.cli.wizard_ui._is_tty", return_value=False):
            status("success message")
            status("failure message", success=False)
            helper("help text\nwith multiple lines")

        captured = capsys.readouterr()
        assert "\033" not in captured.out, (
            f"ANSI escape sequences found in non-TTY output: {captured.out!r}"
        )
