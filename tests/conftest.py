import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_llm():
    """Returns a mock LLM client. All tests use this — never real API calls."""
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="mocked LLM response")
    return llm


@pytest.fixture
def tmp_state_dir(tmp_path):
    """Temporary ~/.agency/ directory for each test."""
    state = tmp_path / ".agency"
    state.mkdir()
    (state / "keys").mkdir()
    return state
