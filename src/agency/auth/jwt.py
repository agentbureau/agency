"""JWT creation and verification using EdDSA (Ed25519) asymmetric signing."""
import time
import jwt


# --- Constants ---
JWT_SCOPE_TASK = "task"
JWT_SCOPE_EVALUATION = "evaluation"
EVALUATOR_JWT_EXPIRY = 86400
JWT_CLOCK_SKEW_LEEWAY = 60
JWT_SCOPE_GRACE_DAYS = 30


def create_jwt(private_key, instance_id: str, client_id: str, jti: str, exp: int | None = None) -> str:
    payload: dict = {"jti": jti, "client_id": client_id, "instance_id": instance_id, "scope": "task", "iat": int(time.time())}
    if exp is not None:
        payload["exp"] = exp
    return jwt.encode(payload, private_key, algorithm="EdDSA")


def verify_jwt(token: str, public_key) -> dict:
    return jwt.decode(
        token, public_key, algorithms=["EdDSA"],
        options={"require": ["iat", "client_id", "instance_id", "scope"]},
        leeway=JWT_CLOCK_SKEW_LEEWAY,
    )


def create_evaluator_jwt(
    private_key,
    instance_id: str,
    client_id: str,
    project_id: str,
    task_id: str,
    agent_composition_id: str = "",
    agent_content_hash: str = "",
    evaluator_agent_id: str = "",
    evaluator_content_hash: str = "",
    task_agent_primitive_ids: dict | None = None,
    exp_seconds: int = EVALUATOR_JWT_EXPIRY,
) -> str:
    from agency.utils.ids import new_uuid
    now = int(time.time())
    payload = {
        "jti": new_uuid(),
        "client_id": client_id,
        "instance_id": instance_id,
        "scope": JWT_SCOPE_EVALUATION,
        "project_id": project_id,
        "task_id": task_id,
        "agent_composition_id": agent_composition_id,
        "agent_content_hash": agent_content_hash,
        "evaluator_agent_id": evaluator_agent_id,
        "evaluator_content_hash": evaluator_content_hash,
        "task_agent_primitive_ids": task_agent_primitive_ids or {},
        "iat": now,
        "exp": now + exp_seconds,
    }
    return jwt.encode(payload, private_key, algorithm="EdDSA")


def is_valid_evaluator_scope(scope: str) -> bool:
    """Accept both 'evaluation' and 'task' scopes during the grace period."""
    return scope in (JWT_SCOPE_EVALUATION, JWT_SCOPE_TASK)
