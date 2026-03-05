import tomllib
import tomli_w
from pathlib import Path

REQUIRED_FIELDS = ["instance_id", "llm_endpoint", "llm_model",
                   "llm_api_key", "contact_email", "oversight_preference"]


class ConfigError(Exception):
    pass


def read_config(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    for field in REQUIRED_FIELDS:
        if field not in cfg:
            raise ConfigError(f"Missing required config field: {field}")
    return cfg


def _strip_none(obj: object) -> object:
    """Recursively remove None values — TOML has no null type."""
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
