import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.compositions import upsert_agent, get_agent, list_agents


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    return conn


def test_upsert_creates_agent(db):
    aid = upsert_agent(db, ["rc-1", "rc-2"], None, None, instance_id="inst-1")
    agent = get_agent(db, aid)
    assert agent is not None
    assert agent["instance_id"] == "inst-1"


def test_upsert_same_composition_returns_same_id(db):
    aid1 = upsert_agent(db, ["rc-1", "rc-2"], None, None, instance_id="inst-1")
    aid2 = upsert_agent(db, ["rc-1", "rc-2"], None, None, instance_id="inst-1")
    assert aid1 == aid2


def test_list_agents_filtered_by_instance(db):
    upsert_agent(db, ["rc-1"], None, None, instance_id="inst-a")
    upsert_agent(db, ["rc-2"], None, None, instance_id="inst-b")
    results = list_agents(db, instance_id="inst-a")
    assert len(results) == 1
    assert results[0]["instance_id"] == "inst-a"
