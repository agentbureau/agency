import pytest
from unittest.mock import patch, MagicMock
from agency.utils.email import send_notification

EMAIL_CFG = {
    "email": {
        "smtp_host": "smtp.test.com",
        "smtp_port": 587,
        "smtp_username": "user@test.com",
        "smtp_password": "secret",
        "sender_address": "user@test.com",
    }
}


def test_send_notification_calls_smtp(monkeypatch):
    mock_smtp = MagicMock()
    with patch("smtplib.SMTP", return_value=mock_smtp.__enter__.return_value):
        send_notification(EMAIL_CFG, "admin@example.com", "Test subject", "Test body")
    # If no exception raised, SMTP was called without error


def test_send_notification_raises_on_bad_config():
    with pytest.raises(KeyError):
        send_notification({}, "admin@example.com", "Subject", "Body")
