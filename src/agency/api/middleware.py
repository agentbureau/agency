from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from agency.auth.jwt import verify_jwt, JWTError

UNPROTECTED = {"/health", "/docs", "/openapi.json", "/redoc"}


class JWTMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret: str):
        super().__init__(app)
        self.secret = secret

    async def dispatch(self, request: Request, call_next):
        if request.url.path in UNPROTECTED:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"detail": "Missing or invalid Authorization header"},
                                status_code=401)
        token = auth.removeprefix("Bearer ")
        try:
            payload = verify_jwt(self.secret, token)
        except JWTError as e:
            return JSONResponse({"detail": str(e)}, status_code=401)

        request.state.jwt_payload = payload
        return await call_next(request)
