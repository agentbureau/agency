import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.templates import insert_template, get_template, list_templates


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    return conn


def test_insert_and_retrieve_template(db):
    tid = insert_template(db, "task_agent", "You are a helpful agent.",
                          instance_id="inst-1")
    t = get_template(db, tid)
    assert t is not None
    assert t["content"] == "You are a helpful agent."
    assert t["template_type"] == "task_agent"
    assert tid.startswith("agt-")


def test_evaluator_template_id_prefix(db):
    tid = insert_template(db, "evaluator", "You evaluate tasks.",
                          instance_id="inst-1")
    assert tid.startswith("evt-")


def test_duplicate_content_rejected(db):
    insert_template(db, "task_agent", "same content", instance_id="inst-1")
    with pytest.raises(Exception):
        insert_template(db, "task_agent", "same content", instance_id="inst-1")


def test_list_templates_by_type(db):
    insert_template(db, "task_agent", "agent template", instance_id="inst-1")
    insert_template(db, "evaluator", "evaluator template", instance_id="inst-1")
    agents = list_templates(db, template_type="task_agent")
    assert len(agents) == 1
    assert agents[0]["template_type"] == "task_agent"
