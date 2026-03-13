"""JWT middleware using EdDSA public-key verification with revocation check."""
import sqlite3

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from agency.auth.jwt import verify_jwt

UNPROTECTED = {"/health", "/docs", "/openapi.json", "/redoc"}


class MissingToken(Exception):
    """Raised when no token is present in the request."""


class TokenRevoked(Exception):
    """Raised when the token's jti has been revoked in issued_tokens."""


def check_token(token: str | None, public_key, conn: sqlite3.Connection) -> dict:
    """Verify a JWT and check revocation status.

    Args:
        token: Raw JWT string, or None if absent.
        public_key: Ed25519 public key object (from cryptography library).
        conn: SQLite connection — must NOT have row_factory set.

    Returns:
        Decoded payload dict.

    Raises:
        MissingToken: token is None.
        TokenRevoked: jti is present and marked revoked in issued_tokens.
        jwt.exceptions.ExpiredSignatureError: token has expired.
        jwt.exceptions.InvalidTokenError: token is otherwise invalid.
    """
    if token is None:
        raise MissingToken()

    payload = verify_jwt(token, public_key)

    jti = payload.get("jti")
    if jti is not None:
        cursor = conn.execute(
            "SELECT revoked FROM issued_tokens WHERE jti = ?", (jti,)
        )
        row = cursor.fetchone()
        if row is not None and row[0] == 1:
            raise TokenRevoked()

    return payload


class JWTMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that validates EdDSA-signed JWTs on every request."""

    def __init__(self, app, public_key, conn: sqlite3.Connection):
        super().__init__(app)
        self.public_key = public_key
        self.conn = conn

    async def dispatch(self, request: Request, call_next):
        if request.url.path in UNPROTECTED:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        token: str | None = None
        if auth.startswith("Bearer "):
            token = auth.removeprefix("Bearer ")

        try:
            payload = check_token(token, self.public_key, self.conn)
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
