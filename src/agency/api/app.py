import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from agency.db.migrations import run_migrations
from agency.status.poller import fetch_status
from agency.api.middleware import JWTMiddleware


def _state_dir() -> Path:
    return Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))


def _jwt_secret() -> str:
    return os.environ.get("AGENCY_JWT_SECRET", "")


def get_db(state_dir: Path) -> sqlite3.Connection:
    db_path = state_dir / "agency.db"
    return sqlite3.connect(db_path, check_same_thread=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    conn = get_db(state_dir)
    run_migrations(conn)
    app.state.db = conn
    app.state.state_dir = state_dir

    cfg_path = state_dir / "agency.toml"
    if cfg_path.exists():
        try:
            from agency.config.toml import read_config
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

    secret = _jwt_secret()
    if secret:
        app.add_middleware(JWTMiddleware, secret=secret)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "1.0.0"}

    from agency.api.routes import tasks, projects, primitives, evolution
    app.include_router(tasks.router)
    app.include_router(projects.router)
    app.include_router(primitives.router)
    app.include_router(evolution.router)

    return app


app = create_app()
