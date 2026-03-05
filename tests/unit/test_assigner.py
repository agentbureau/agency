import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive
from agency.engine.assigner import assign_agent


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    insert_primitive(conn, "role_components",
                     description="evaluate task quality and completeness",
                     instance_id="inst-1")
    insert_primitive(conn, "desired_outcomes",
                     description="produce a detailed quality assessment",
                     instance_id="inst-1")
    insert_primitive(conn, "trade_off_configs",
                     description="rigour over speed",
                     instance_id="inst-1")
    return conn


def test_assign_returns_agent_id(db):
    task = {"task_description": "grade this submission", "instance_id": "inst-1"}
    result = assign_agent(db, "task-1", task)
    assert result["agent_id"]
    assert result["rendered_prompt"]


def test_rendered_prompt_contains_task(db):
    task = {"task_description": "grade this submission", "instance_id": "inst-1"}
    result = assign_agent(db, "task-1", task)
    assert "grade this submission" in result["rendered_prompt"]


def test_same_task_returns_same_agent(db):
    task = {"task_description": "grade this submission", "instance_id": "inst-1"}
    r1 = assign_agent(db, "task-1", task)
    r2 = assign_agent(db, "task-2", task)
    assert r1["agent_id"] == r2["agent_id"]
