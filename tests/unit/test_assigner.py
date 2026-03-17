import json
import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive
from agency.db.compositions import get_agent
from agency.engine.assigner import assign_agent
from agency.utils.hashing import content_hash


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


def test_content_hash_matches_db(db):
    """assigner.py hash must match agents.content_hash stored by compositions.py."""
    task = {"task_description": "grade this submission", "instance_id": "inst-1"}
    result = assign_agent(db, "task-1", task)
    agent = get_agent(db, result["agent_id"])
    assert agent is not None
    assert result["content_hash"] == agent["content_hash"]


@pytest.fixture
def db_multi_role(tmp_path):
    """DB with multiple role components to test hash consistency with 2+ primitives."""
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    insert_primitive(conn, "role_components",
                     description="evaluate task quality and completeness",
                     instance_id="inst-1")
    insert_primitive(conn, "role_components",
                     description="check for security vulnerabilities in code",
                     instance_id="inst-1")
    insert_primitive(conn, "role_components",
                     description="review documentation accuracy",
                     instance_id="inst-1")
    insert_primitive(conn, "desired_outcomes",
                     description="produce a detailed quality assessment",
                     instance_id="inst-1")
    insert_primitive(conn, "trade_off_configs",
                     description="rigour over speed",
                     instance_id="inst-1")
    return conn


def test_content_hash_matches_db_multi_role(db_multi_role):
    """With 2+ role components, assigner hash must still match DB hash."""
    task = {"task_description": "review this code for quality and security", "instance_id": "inst-1"}
    result = assign_agent(db_multi_role, "task-1", task)
    agent = get_agent(db_multi_role, result["agent_id"])
    assert agent is not None
    assert result["content_hash"] == agent["content_hash"]
    # Verify the hash uses json.dumps(sorted(...))
    role_ids = json.loads(agent["role_component_ids"])
    expected_hash = content_hash(json.dumps(sorted(role_ids)))
    assert result["content_hash"] == expected_hash


def test_template_id_stored_in_agent(db):
    """upsert_agent should store template_id in the agents table."""
    task = {"task_description": "grade this submission", "instance_id": "inst-1"}
    result = assign_agent(db, "task-1", task)
    agent = get_agent(db, result["agent_id"])
    assert agent is not None
    assert agent["template_id"] == "default"
