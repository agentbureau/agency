"""JWT creation and verification using EdDSA (Ed25519) asymmetric signing."""
import time
import jwt


def create_jwt(private_key, instance_id: str, client_id: str, jti: str, exp: int | None = None) -> str:
    payload: dict = {"jti": jti, "client_id": client_id, "instance_id": instance_id, "scope": "task", "iat": int(time.time())}
    if exp is not None:
        payload["exp"] = exp
    return jwt.encode(payload, private_key, algorithm="EdDSA")


def verify_jwt(token: str, public_key) -> dict:
    return jwt.decode(token, public_key, algorithms=["EdDSA"], options={"require": ["iat", "client_id", "instance_id", "scope"]})


def create_evaluator_jwt(private_key, instance_id: str, client_id: str, project_id: str, task_id: str, exp_seconds: int = 86400) -> str:
    now = int(time.time())
    payload = {"client_id": client_id, "instance_id": instance_id, "scope": "task", "project_id": project_id, "task_id": task_id, "iat": now, "exp": now + exp_seconds}
    return jwt.encode(payload, private_key, algorithm="EdDSA")
