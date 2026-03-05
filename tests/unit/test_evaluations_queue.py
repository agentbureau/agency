import sqlite3
import pytest
from agency.db.migrations import run_migrations
from agency.db.evaluations import (
    enqueue_evaluation, get_pending_evaluations, confirm_evaluation
)


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    return conn


def test_enqueue_and_retrieve(db):
    eid = enqueue_evaluation(db, '{"score": 0.8}')
    pending = get_pending_evaluations(db)
    assert len(pending) == 1
    assert pending[0]["id"] == eid


def test_confirmed_evaluation_not_in_pending(db):
    eid = enqueue_evaluation(db, '{"score": 0.9}')
    confirm_evaluation(db, eid)
    pending = get_pending_evaluations(db)
    assert len(pending) == 0


def test_filter_by_destination(db):
    enqueue_evaluation(db, '{"score": 0.7}', destination="agency_instance")
    enqueue_evaluation(db, '{"score": 0.6}', destination="home_pool")
    local = get_pending_evaluations(db, destination="agency_instance")
    assert len(local) == 1
