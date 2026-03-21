"""Tests for GET /tasks/{task_id} endpoint, reconstruct_rendered_prompt,
get_evaluation_by_task_id, and agent_hash status fix."""
import json
import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive
from agency.db.tasks import create_task, set_task_composition
from agency.db.evaluations import enqueue_evaluation, get_evaluation_by_task_id
from agency.engine.assigner import assign_agent
from agency.engine.renderer import reconstruct_rendered_prompt


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    insert_primitive(conn, "role_components",
                     description="grade and evaluate submission quality and completeness",
                     instance_id="inst-1")
    insert_primitive(conn, "desired_outcomes",
                     description="produce a detailed grading assessment of the submission",
                     instance_id="inst-1")
    insert_primitive(conn, "trade_off_configs",
                     description="rigour over speed when grading submissions",
                     instance_id="inst-1")
    return conn


# ---------------------------------------------------------------------------
# get_evaluation_by_task_id
# ---------------------------------------------------------------------------


def test_get_evaluation_returns_none_when_no_evaluation(db):
    tid = create_task(db, description="test task", project_id="p1")
    assert get_evaluation_by_task_id(db, tid) is None


def test_get_evaluation_returns_evaluation_when_present(db):
    tid = create_task(db, description="test task", project_id="p1")
    eval_data = json.dumps({
        "output": "looks good",
        "score": 85,
        "score_type": "percentage",
        "task_completed": True,
    })
    enqueue_evaluation(db, eval_data, tid)
    result = get_evaluation_by_task_id(db, tid)
    assert result is not None
    assert result["evaluation_status"] == "pending"
    assert result["output"] == "looks good"
    assert result["score"] == 85
    assert result["score_type"] == "percentage"
    assert result["task_completed"] is True
    assert result["submitted_at"] is not None
    assert result["content_hash"] is not None


# ---------------------------------------------------------------------------
# reconstruct_rendered_prompt
# ---------------------------------------------------------------------------


def test_reconstruct_returns_prompt_for_assigned_task(db):
    task = {"task_description": "grade this submission", "instance_id": "inst-1"}
    result = assign_agent(db, "task-1", task)
    tid = create_task(db, description="grade this submission", project_id="p1")
    set_task_composition(db, tid, result["agent_id"])

    render = reconstruct_rendered_prompt(db, tid)
    assert "grade this submission" in render["rendered_prompt"]
    assert render["rendering_warnings"] == []


def test_reconstruct_warns_on_deleted_primitive(db):
    task = {"task_description": "grade this submission", "instance_id": "inst-1"}
    result = assign_agent(db, "task-1", task)
    tid = create_task(db, description="grade this submission", project_id="p1")
    set_task_composition(db, tid, result["agent_id"])

    # Delete a role component
    role_ids = json.loads(
        db.execute("SELECT role_component_ids FROM agents WHERE id = ?",
                   (result["agent_id"],)).fetchone()[0]
    )
    db.execute("DELETE FROM role_components WHERE id = ?", (role_ids[0],))
    db.commit()

    render = reconstruct_rendered_prompt(db, tid)
    assert len(render["rendering_warnings"]) > 0
    assert "deleted" in render["rendering_warnings"][0].lower()
    assert "[primitive deleted:" in render["rendered_prompt"]


def test_reconstruct_returns_empty_when_no_composition(db):
    tid = create_task(db, description="test", project_id="p1")
    render = reconstruct_rendered_prompt(db, tid)
    assert render["rendered_prompt"] == ""
    assert len(render["rendering_warnings"]) > 0


# ---------------------------------------------------------------------------
# agent_hash resolution (status endpoint pattern)
# ---------------------------------------------------------------------------


def test_agent_hash_is_content_hash_not_uuid(db):
    """agent_hash in the status query should be agents.content_hash (SHA-256),
    not agent_composition_id (UUID)."""
    from agency.db.projects import create_project

    pid = create_project(db, name="Test", client_id="c1", description=None, admin_email=None)
    task = {"task_description": "test", "instance_id": "inst-1"}
    result = assign_agent(db, "task-1", task)
    tid = create_task(db, description="test", project_id=pid)
    set_task_composition(db, tid, result["agent_id"])

    # Query using the same JOIN pattern as the fixed status endpoint
    row = db.execute(
        """
        SELECT t.id, a.content_hash AS agent_hash
        FROM tasks t
        LEFT JOIN agents a ON a.id = t.agent_composition_id
        WHERE t.id = ?
        """,
        (tid,),
    ).fetchone()

    assert row is not None
    agent_hash = row[1]
    # agent_hash should be a SHA-256 hex string (64 chars), not a UUID
    assert len(agent_hash) == 64
    assert agent_hash == result["content_hash"]
