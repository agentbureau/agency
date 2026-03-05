import jwt as pyjwt
import uuid
import time


class JWTError(Exception):
    pass


def create_task_manager_jwt(secret: str, client_id: str,
                             instance_id: str, scope: str) -> str:
    return pyjwt.encode({
        "jti": str(uuid.uuid4()),
        "client_id": client_id,
        "instance_id": instance_id,
        "scope": scope,
        "iat": int(time.time()),
    }, secret, algorithm="HS256")


def create_evaluator_jwt(secret: str, instance_id: str, client_id: str,
                          project_id: str, task_id: str,
                          expiry_seconds: int = 86400) -> str:
    return pyjwt.encode({
        "jti": str(uuid.uuid4()),
        "instance_id": instance_id,
        "client_id": client_id,
        "project_id": project_id,
        "task_id": task_id,
        "exp": int(time.time()) + expiry_seconds,
    }, secret, algorithm="HS256")


def verify_jwt(secret: str, token: str) -> dict:
    try:
        return pyjwt.decode(token, secret, algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError:
        raise JWTError("expired")
    except pyjwt.InvalidTokenError as e:
        raise JWTError(str(e))
