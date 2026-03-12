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


def get_db(state_dir: Path) -> sqlite3.Connection:
    db_path = state_dir / "agency.db"
    return sqlite3.connect(db_path, check_same_thread=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger(__name__)

    # Step 1: Resolve AGENCY_STATE_DIR, confirm agency.toml exists
    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    # Step 2: Load and parse agency.toml
    cfg = {}
    cfg_path = state_dir / "agency.toml"
    if cfg_path.exists():
        try:
            cfg = load_config(cfg_path)
        except ConfigError:
            pass

    # Step 3: Load Ed25519 public key — REQUIRED; abort with clear error if missing
    pub_key_path = state_dir / "keys" / "agency.ed25519.pub.pem"
    priv_key_path = state_dir / "keys" / "agency.ed25519.pem"
    if not pub_key_path.exists():
        raise RuntimeError(
            f"Ed25519 public key not found at {pub_key_path}. "
            "Run 'agency init' to generate keypair."
        )
    from agency.auth.keypair import load_public_key, load_private_key
    public_key = load_public_key(str(pub_key_path))
    private_key = None
    if priv_key_path.exists():
        private_key = load_private_key(str(priv_key_path))

    # Step 4: Open SQLite; create if absent
    conn = get_db(state_dir)

    # Step 5: Enable WAL mode — log warning on failure, do NOT abort
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception as e:
        logger.warning("WAL mode could not be enabled: %s", e)

    # Step 6: Run migrations
    run_migrations(conn)

    app.state.db = conn
    app.state.state_dir = state_dir
    app.state.public_key = public_key
    app.state.private_key = private_key
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
    app = FastAPI(title="Agency", version="1.2.0", lifespan=lifespan)

    @app.middleware("http")
    async def jwt_middleware(request, call_next):
        from agency.api.middleware import UNPROTECTED, check_token, MissingToken, TokenRevoked
        if request.url.path in UNPROTECTED:
            return await call_next(request)

        public_key = getattr(request.app.state, "public_key", None)

        conn = request.app.state.db
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else None

        try:
            payload = check_token(token, public_key, conn)
        except MissingToken:
            return JSONResponse(
                {"detail": "Missing or invalid Authorization header"}, status_code=401
            )
        except TokenRevoked:
            return JSONResponse({"detail": "Token has been revoked"}, status_code=401)
        except Exception as exc:
            return JSONResponse({"detail": str(exc)}, status_code=401)

        request.state.jwt_payload = payload
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "1.2.0"}

    from agency.api.routes import tasks, projects, primitives, evolution
    app.include_router(tasks.router)
    app.include_router(projects.router)
    app.include_router(primitives.router)
    app.include_router(evolution.router)

    return app


app = create_app()
