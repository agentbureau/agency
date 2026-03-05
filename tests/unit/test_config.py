import pytest
from agency.config.toml import write_config, read_config, ConfigError


def test_write_and_read_roundtrip(tmp_path):
    cfg = {
        "instance_id": "test-id-123",
        "llm_endpoint": "https://api.anthropic.com",
        "llm_model": "claude-sonnet-4-6",
        "llm_api_key": "sk-test",
        "contact_email": "test@example.com",
        "oversight_preference": "discretion",
        "error_notification_timeout": 300,
        "home_pool": {
            "registered": False,
            "enabled": False,
            "endpoint": None,
        },
        "status": {
            "url": "https://raw.githubusercontent.com/[owner]/agency/main/agency-status.json",
            "last_checked": None,
        },
    }
    path = tmp_path / "agency.toml"
    write_config(cfg, path)
    loaded = read_config(path)
    assert loaded["instance_id"] == "test-id-123"
    assert loaded["home_pool"]["registered"] is False


def test_read_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        read_config(tmp_path / "nonexistent.toml")


def test_missing_required_field_raises(tmp_path):
    path = tmp_path / "agency.toml"
    path.write_text("[home_pool]\nregistered = false\n")
    with pytest.raises(ConfigError, match="instance_id"):
        read_config(path)
