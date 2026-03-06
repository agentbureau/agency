import tomllib
import tomli_w
from pathlib import Path

REQUIRED_FIELDS = [
    "instance_id", "llm_endpoint", "llm_model", "llm_api_key",
    "contact_email", "oversight_preference",
    "auth.jwt_secret",
    "server.host", "server.port",
    "email.smtp_host", "email.smtp_port",
    "email.smtp_username", "email.smtp_password", "email.sender_address",
]


class ConfigError(Exception):
    pass


def load_config(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with open(path, "rb") as f:
        return tomllib.load(f)


def validate_config(cfg: dict) -> None:
    for field in REQUIRED_FIELDS:
        parts = field.split(".")
        obj = cfg
        for part in parts:
            if not isinstance(obj, dict) or part not in obj:
                raise ConfigError(f"Missing required config field: {field}")
            obj = obj[part]


def read_config(path: Path) -> dict:
    cfg = load_config(path)
    validate_config(cfg)
    return cfg


def _strip_none(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: _strip_none(v) for k, v in obj.items() if v is not None}
    return obj


def write_config(cfg: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(_strip_none(cfg), f)


def default_config(instance_id: str) -> dict:
    return {
        "instance_id": instance_id,
        "llm_endpoint": "https://api.anthropic.com/v1",
        "llm_model": "",
        "llm_api_key": "",
        "contact_email": "",
        "oversight_preference": "discretion",
        "error_notification_timeout": 300,
        "auth": {
            "jwt_secret": "",
        },
        "server": {
            "host": "127.0.0.1",
            "port": 8000,
        },
        "email": {
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_username": "",
            "smtp_password": "",
            "sender_address": "",
        },
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
