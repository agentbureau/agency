import os
import click
import uvicorn
from pathlib import Path
from agency.config.toml import load_config, write_config, ConfigError


def _state_dir() -> Path:
    return Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))


@click.command("serve")
@click.option("--host", default=None, help="Host to bind (overrides agency.toml)")
@click.option("--port", default=None, type=int, help="Port to bind (overrides agency.toml)")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload")
def serve_command(host: str | None, port: int | None, reload: bool):
    """Start the Agency API server."""
    state_dir = _state_dir()
    cfg_path = state_dir / "agency.toml"

    cfg = {}
    if cfg_path.exists():
        try:
            cfg = load_config(cfg_path)
        except ConfigError as e:
            raise click.ClickException(str(e))

    resolved_host = host or cfg.get("server", {}).get("host", "127.0.0.1")
    resolved_port = port or cfg.get("server", {}).get("port", 8000)

    # Write back if CLI flags differ from stored values
    if cfg and (host or port):
        cfg.setdefault("server", {})
        if host and cfg["server"].get("host") != host:
            cfg["server"]["host"] = host
            write_config(cfg, cfg_path)
        if port and cfg["server"].get("port") != port:
            cfg["server"]["port"] = port
            write_config(cfg, cfg_path)

    uvicorn.run(
        "agency.api.app:app",
        host=resolved_host,
        port=resolved_port,
        reload=reload,
    )
