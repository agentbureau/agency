import os
import sqlite3
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from agency.db.migrations import run_migrations
from agency.status.poller import fetch_status
from agency.config.toml import load_config, ConfigError


def _state_dir() -> Path:
    return Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))


def _resolve_jwt_secret(cfg: dict) -> str:
    """Env var overrides toml. Returns empty string if absent from both."""
    return os.environ.get("AGENCY_JWT_SECRET") or cfg.get("auth", {}).get("jwt_secret", "")


def get_db(state_dir: Path) -> sqlite3.Connection:
    db_path = state_dir / "agency.db"
    return sqlite3.connect(db_path, check_same_thread=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    cfg = {}
    cfg_path = state_dir / "agency.toml"
    if cfg_path.exists():
        try:
            cfg = load_config(cfg_path)
        except ConfigError:
            pass

    secret = _resolve_jwt_secret(cfg)

    conn = get_db(state_dir)
    run_migrations(conn)

    app.state.db = conn
    app.state.state_dir = state_dir
    app.state.jwt_secret = secret
    app.state.config = cfg

    status_url = cfg.get("status", {}).get("url")
    if status_url:
        try:
            fetch_status(status_url)
        except Exception:
            pass

    yield
    conn.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Agency", version="1.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def jwt_middleware(request, call_next):
        from agency.api.middleware import UNPROTECTED
        from agency.auth.jwt import verify_jwt, JWTError
        if request.url.path in UNPROTECTED:
            return await call_next(request)
        secret = request.app.state.jwt_secret
        if not secret:
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"detail": "Missing or invalid Authorization header"},
                                status_code=401)
        token = auth.removeprefix("Bearer ")
        try:
            payload = verify_jwt(secret, token)
        except JWTError as e:
            return JSONResponse({"detail": str(e)}, status_code=401)
        request.state.jwt_payload = payload
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "1.1.0"}

    from agency.api.routes import tasks, projects, primitives, evolution
    app.include_router(tasks.router)
    app.include_router(projects.router)
    app.include_router(primitives.router)
    app.include_router(evolution.router)

    return app


app = create_app()
