import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
import os

from fastapi import FastAPI

from agency.db.migrations import run_migrations
from agency.status.poller import fetch_status


def _state_dir() -> Path:
    return Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))


def _get_db_conn(state_dir: Path) -> sqlite3.Connection:
    db_path = state_dir / "agency.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    conn = _get_db_conn(state_dir)
    run_migrations(conn)
    app.state.db = conn

    cfg_path = state_dir / "agency.toml"
    if cfg_path.exists():
        from agency.config.toml import read_config
        try:
            cfg = read_config(cfg_path)
            status_url = cfg.get("status", {}).get("url")
            if status_url:
                fetch_status(status_url)
        except Exception:
            pass

    yield

    conn.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Agency", version="1.0.0", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "1.0.0"}

    return app


app = create_app()
