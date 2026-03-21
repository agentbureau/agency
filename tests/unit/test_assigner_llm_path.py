"""Tests for Track C2: LLM assigner path behind feature flag (§4.4.3).

Covers feature flag reading, fallback on subprocess errors, timeout,
JSON parse failure, and fallback log file creation. All tests use
mocked subprocess.run — no real LLM calls.
"""

import json
import sqlite3
import subprocess
from unittest import mock

import pytest

from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive
from agency.engine.assigner import assign_agent, _log_fallback
from agency.engine.constants import (
    ASSIGNER_STRATEGY_KEY,
    ASSIGNER_STRATEGY_EMBEDDING,
    ASSIGNER_STRATEGY_LLM,
    ASSIGNER_LLM_TIMEOUT,
    ASSIGNER_FALLBACK_LOG,
)


@pytest.fixture
def db_with_primitives(tmp_path):
    """DB with primitives sufficient for embedding path."""
    conn = sqlite3.connect(tmp_path / "agency.db")
    run_migrations(conn)
    insert_primitive(conn, "role_components",
                     description="review code for correctness and security vulnerabilities",
                     instance_id="inst-1")
    insert_primitive(conn, "role_components",
                     description="analyse data quality in datasets",
                     instance_id="inst-1")
    insert_primitive(conn, "desired_outcomes",
                     description="produce a thorough code quality assessment",
                     instance_id="inst-1")
    insert_primitive(conn, "trade_off_configs",
                     description="rigour over speed when reviewing code",
                     instance_id="inst-1")
    return conn


@pytest.fixture
def llm_cfg():
    """Config that activates the LLM strategy."""
    return {"assigner": {ASSIGNER_STRATEGY_KEY: ASSIGNER_STRATEGY_LLM}}


@pytest.fixture
def embedding_cfg():
    """Config that explicitly selects the embedding strategy."""
    return {"assigner": {ASSIGNER_STRATEGY_KEY: ASSIGNER_STRATEGY_EMBEDDING}}


TASK = {"task_description": "review this Python code for security issues", "instance_id": "inst-1"}


def test_embedding_strategy_by_default(db_with_primitives):
    """assign_agent uses embedding path when cfg has no strategy."""
    result = assign_agent(db_with_primitives, "task-1", TASK, cfg=None)
    assert result["agent_id"]
    assert result["composition_fitness"]
    # No LLM-specific keys in fitness when using embedding path
    assert "fitness_verdict" not in result["composition_fitness"]


def test_embedding_strategy_when_explicit(db_with_primitives, embedding_cfg):
    """cfg={"assigner": {"strategy": "embedding"}} uses embedding path."""
    result = assign_agent(db_with_primitives, "task-1", TASK, cfg=embedding_cfg)
    assert result["agent_id"]
    assert result["composition_fitness"]
    assert "fitness_verdict" not in result["composition_fitness"]


@mock.patch("agency.engine.assigner.subprocess.run")
def test_llm_strategy_falls_back_on_subprocess_error(
    mock_run, db_with_primitives, llm_cfg, tmp_path,
):
    """When subprocess.run raises OSError, embedding fallback is used and logged."""
    mock_run.side_effect = OSError("claude not found")

    with mock.patch("agency.engine.assigner.ASSIGNER_FALLBACK_LOG",
                    str(tmp_path / "fallback.log")):
        result = assign_agent(db_with_primitives, "task-err", TASK, cfg=llm_cfg)

    # Should still produce a valid result via embedding fallback
    assert result["agent_id"]
    assert result["composition_fitness"]
    # No LLM-specific keys — fell back to embedding
    assert "fitness_verdict" not in result["composition_fitness"]

    # Fallback log should exist
    log_path = tmp_path / "fallback.log"
    assert log_path.exists()
    entry = json.loads(log_path.read_text().strip().split("\n")[0])
    assert entry["task_id"] == "task-err"
    assert entry["failure_mode"] == "api_error"
    assert entry["strategy_used"] == "embedding"


@mock.patch("agency.engine.assigner.subprocess.run")
def test_llm_strategy_falls_back_on_timeout(
    mock_run, db_with_primitives, llm_cfg, tmp_path,
):
    """subprocess.TimeoutExpired triggers embedding fallback."""
    mock_run.side_effect = subprocess.TimeoutExpired(
        cmd=["claude"], timeout=ASSIGNER_LLM_TIMEOUT,
    )

    with mock.patch("agency.engine.assigner.ASSIGNER_FALLBACK_LOG",
                    str(tmp_path / "fallback.log")):
        result = assign_agent(db_with_primitives, "task-timeout", TASK, cfg=llm_cfg)

    assert result["agent_id"]
    assert "fitness_verdict" not in result["composition_fitness"]

    log_path = tmp_path / "fallback.log"
    assert log_path.exists()
    entry = json.loads(log_path.read_text().strip().split("\n")[0])
    assert entry["failure_mode"] == "timeout"
    assert entry["slot_affected"] == "all"


@mock.patch("agency.engine.assigner.subprocess.run")
def test_llm_strategy_falls_back_on_parse_error(
    mock_run, db_with_primitives, llm_cfg, tmp_path,
):
    """Invalid JSON triggers retry then embedding fallback."""
    mock_result = mock.Mock()
    mock_result.returncode = 0
    mock_result.stdout = "not valid json at all"
    mock_result.stderr = ""
    mock_run.return_value = mock_result

    with mock.patch("agency.engine.assigner.ASSIGNER_FALLBACK_LOG",
                    str(tmp_path / "fallback.log")):
        result = assign_agent(db_with_primitives, "task-parse", TASK, cfg=llm_cfg)

    assert result["agent_id"]
    assert "fitness_verdict" not in result["composition_fitness"]

    # subprocess.run should have been called twice (initial + 1 retry)
    assert mock_run.call_count == 2

    log_path = tmp_path / "fallback.log"
    assert log_path.exists()
    entry = json.loads(log_path.read_text().strip().split("\n")[0])
    assert entry["failure_mode"] == "parse"


def test_fallback_log_written(tmp_path):
    """_log_fallback creates the log file with correct JSON structure."""
    log_file = tmp_path / "subdir" / "fallback.log"

    with mock.patch("agency.engine.assigner.ASSIGNER_FALLBACK_LOG", str(log_file)):
        _log_fallback("task-123", "timeout", "all", "timed out after 30s")

    assert log_file.exists()
    entry = json.loads(log_file.read_text().strip())
    assert entry["task_id"] == "task-123"
    assert entry["failure_mode"] == "timeout"
    assert entry["slot_affected"] == "all"
    assert entry["detail"] == "timed out after 30s"
    assert entry["strategy_used"] == "embedding"
    assert "timestamp" in entry
