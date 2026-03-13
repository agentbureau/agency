import pytest
from agency.config.toml import write_config, read_config, load_config, validate_config, ConfigError


def _make_full_config() -> dict:
    return {
        "instance_id": "test-id-123",
        "server": {
            "host": "127.0.0.1",
            "port": 8000,
        },
        "llm": {
            "backend": "claude-code",
            "model": "claude-sonnet-4-6",
            "endpoint": "",
            "api_key": "",
        },
        "notifications": {
            "contact_email": "test@example.com",
            "oversight_preference": "discretion",
            "error_notification_timeout": 300,
        },
        "output": {
            "attribution": True,
        },
        "home_pool": {
            "registered": False,
            "enabled": False,
        },
        "status": {
            "url": "https://raw.githubusercontent.com/[owner]/agency/main/agency-status.json",
        },
    }


def test_write_and_read_roundtrip(tmp_path):
    cfg = _make_full_config()
    path = tmp_path / "agency.toml"
    write_config(cfg, path)
    loaded = load_config(path)
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


# --- New tests for split load_config / validate_config ---

def test_load_config_returns_raw_dict(tmp_path):
    p = tmp_path / "agency.toml"
    p.write_bytes(b'instance_id = "abc"\n')
    cfg = load_config(p)
    assert cfg["instance_id"] == "abc"


def test_load_config_raises_if_file_missing(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.toml")


def test_validate_config_passes_when_all_fields_present():
    cfg = _make_full_config()
    validate_config(cfg)  # should not raise


def test_validate_config_raises_on_missing_top_level():
    cfg = _make_full_config()
    del cfg["instance_id"]
    with pytest.raises(ConfigError, match="instance_id"):
        validate_config(cfg)


def test_validate_config_raises_on_missing_server_host():
    cfg = _make_full_config()
    del cfg["server"]["host"]
    with pytest.raises(ConfigError, match="server.host"):
        validate_config(cfg)


def test_validate_config_raises_on_missing_server_port():
    cfg = _make_full_config()
    del cfg["server"]["port"]
    with pytest.raises(ConfigError, match="server.port"):
        validate_config(cfg)


def test_read_config_is_load_plus_validate(tmp_path):
    p = tmp_path / "agency.toml"
    write_config(_make_full_config(), p)
    cfg = read_config(p)
    assert "instance_id" in cfg


# --- v1.2.0 new section tests ---

def test_config_without_jwt_secret_is_valid():
    """v1.2.0: jwt_secret is removed from required fields."""
    cfg = {
        "instance_id": "inst-1",
        "server": {"host": "127.0.0.1", "port": 8000},
        "llm": {"backend": "claude-code", "model": "claude-sonnet-4-6"},
        "notifications": {"contact_email": "test@example.com", "oversight_preference": "discretion", "error_notification_timeout": 1800},
        "output": {"attribution": True},
    }
    from agency.config.toml import validate_config
    validate_config(cfg)  # should not raise


def test_config_with_llm_section(tmp_path):
    cfg = {
        "instance_id": "inst-1",
        "llm": {"backend": "claude-code", "model": "claude-sonnet-4-6", "endpoint": "", "api_key": ""},
        "notifications": {"contact_email": "a@b.com", "oversight_preference": "discretion", "error_notification_timeout": 1800},
        "output": {"attribution": True},
        "server": {"host": "127.0.0.1", "port": 8000},
    }
    from agency.config.toml import write_config, load_config
    path = tmp_path / "agency.toml"
    write_config(cfg, str(path))
    loaded = load_config(str(path))
    assert loaded["llm"]["backend"] == "claude-code"


def test_config_with_smtp_section(tmp_path):
    cfg = {
        "instance_id": "inst-1",
        "llm": {"backend": "api", "model": "claude-sonnet-4-6", "endpoint": "https://api.anthropic.com/v1", "api_key": "sk-..."},
        "notifications": {"contact_email": "a@b.com", "oversight_preference": "discretion", "error_notification_timeout": 1800},
        "output": {"attribution": True},
        "server": {"host": "127.0.0.1", "port": 8000},
        "smtp": {"host": "smtp.gmail.com", "port": 587, "username": "u", "password": "p", "from_address": "u@gmail.com"},
    }
    from agency.config.toml import write_config, load_config
    path = tmp_path / "agency.toml"
    write_config(cfg, str(path))
    loaded = load_config(str(path))
    assert loaded["smtp"]["host"] == "smtp.gmail.com"
