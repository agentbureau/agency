import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive
from agency.engine.evaluator import build_evaluator
from agency.auth.keypair import generate_keypair, load_private_key, load_public_key


@pytest.fixture
def keypair(tmp_path):
    priv = str(tmp_path / "key.pem")
    pub = str(tmp_path / "key.pub.pem")
    generate_keypair(priv, pub)
    return load_private_key(priv), load_public_key(pub)


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    insert_primitive(conn, "role_components",
                     description="assess and score task output",
                     instance_id="inst-1")
    insert_primitive(conn, "desired_outcomes",
                     description="produce structured evaluation report",
                     instance_id="inst-1")
    insert_primitive(conn, "trade_off_configs",
                     description="rigour over speed",
                     instance_id="inst-1")
    return conn


def test_evaluator_has_callback_jwt(db, keypair):
    private_key, _ = keypair
    task = {"task_description": "grade this essay", "instance_id": "inst-1"}
    result = build_evaluator(db, "task-1", task, private_key, "inst-1")
    assert result["callback_jwt"]
    assert result["rendered_prompt"]


def test_callback_jwt_in_rendered_prompt(db, keypair):
    private_key, _ = keypair
    task = {"task_description": "grade this essay", "instance_id": "inst-1"}
    result = build_evaluator(db, "task-1", task, private_key, "inst-1")
    assert result["callback_jwt"] in result["rendered_prompt"]


def test_callback_jwt_contains_task_id(db, keypair):
    from agency.auth.jwt import verify_jwt
    private_key, public_key = keypair
    task = {"task_description": "grade this essay", "instance_id": "inst-1"}
    result = build_evaluator(db, "task-1", task, private_key, "inst-1")
    payload = verify_jwt(result["callback_jwt"], public_key)
    assert payload["task_id"] == "task-1"
