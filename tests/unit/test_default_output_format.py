"""Test that default output format is markdown (Issue 7, v1.2.4)."""
from agency.models.tasks import TaskRequest, BatchTaskRequest


def test_task_request_default_markdown():
    req = TaskRequest(task_description="test")
    assert req.output_format == "markdown"


def test_batch_task_request_default_markdown():
    req = BatchTaskRequest(description="test")
    assert req.output_format is None  # batch uses None, falls back to markdown in renderer
