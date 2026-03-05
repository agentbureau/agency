import pytest
from agency.auth.jwt import (
    create_task_manager_jwt, create_evaluator_jwt,
    verify_jwt, JWTError
)

INSTANCE_ID = "inst-001"
CLIENT_ID = "client-001"
PROJECT_ID = "proj-001"
TASK_ID = "task-001"
SECRET = "test-secret-key"


def test_task_manager_jwt_verifies():
    token = create_task_manager_jwt(SECRET, CLIENT_ID, INSTANCE_ID, scope="task")
    payload = verify_jwt(SECRET, token)
    assert payload["client_id"] == CLIENT_ID


def test_evaluator_jwt_contains_task_id():
    token = create_evaluator_jwt(SECRET, INSTANCE_ID, CLIENT_ID,
                                  PROJECT_ID, TASK_ID, expiry_seconds=3600)
    payload = verify_jwt(SECRET, token)
    assert payload["task_id"] == TASK_ID


def test_expired_jwt_raises():
    token = create_evaluator_jwt(SECRET, INSTANCE_ID, CLIENT_ID,
                                  PROJECT_ID, TASK_ID, expiry_seconds=-1)
    with pytest.raises(JWTError, match="expired"):
        verify_jwt(SECRET, token)


def test_task_id_mismatch_raises():
    token = create_evaluator_jwt(SECRET, INSTANCE_ID, CLIENT_ID,
                                  PROJECT_ID, TASK_ID, expiry_seconds=3600)
    payload = verify_jwt(SECRET, token)
    assert payload["task_id"] != "wrong-task-id"
