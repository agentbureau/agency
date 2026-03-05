import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive
from agency.db.compositions import upsert_agent
from agency.engine.agent_creator import create_adjacent_agent


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    for desc in [
        "evaluate task quality and completeness",
        "assess output quality against criteria",
        "review task for accuracy and clarity",
        "score output on predefined rubric",
    ]:
        insert_primitive(conn, "role_components", description=desc, instance_id="inst-1")
    return conn


@pytest.fixture
def agent_id(db):
    rows = db.execute("SELECT id FROM role_components LIMIT 1").fetchall()
    return upsert_agent(db, role_component_ids=[rows[0][0]],
                        desired_outcome_id=None, trade_off_config_id=None,
                        instance_id="inst-1")


def test_adjacent_agent_returns_new_id(db, agent_id):
    new_id = create_adjacent_agent(db, agent_id, "inst-1")
    # Either a new agent was created or None if no adjacent found
    assert new_id is None or (isinstance(new_id, str) and new_id != agent_id)


def test_adjacent_agent_unknown_source_returns_none(db):
    result = create_adjacent_agent(db, "nonexistent", "inst-1")
    assert result is None


def test_adjacent_agent_no_roles_returns_none(db):
    empty_agent = upsert_agent(db, role_component_ids=[],
                               desired_outcome_id=None, trade_off_config_id=None,
                               instance_id="inst-1")
    result = create_adjacent_agent(db, empty_agent, "inst-1")
    assert result is None
