# Agency Caller Protocol

This document defines the contract between Agency (the agent composer) and the requester (the system that executes tasks). Agency composes agents; the requester executes them. The requester is responsible for the full assign → execute → evaluate loop.

## Terminology

- **Agency** — the composition service. Selects primitives, composes agents, records evaluations.
- **Requester** — the system calling Agency's tools. Executes tasks using returned prompts. In Claude Code, the requester is the LLM session via MCP tools. In Workgraph, the requester is a shell script calling the HTTP API.

## The loop

### Step 1: Assign

Call `agency_assign` with one or more tasks. Each task needs an `external_id` (your identifier) and a `description` (what the task requires).

Agency returns:
- **`assignments`** — maps each `external_id` to an `agency_task_id` and `agent_hash`
- **`agents`** — maps each `agent_hash` to a `rendered_prompt` (the composed agent)

The `agency_task_id` is Agency's identifier for the task. Use it (not your `external_id`) in all subsequent calls.

### Step 2: Execute

For each task, read the `rendered_prompt` from the `agents` map (using the `agent_hash` from the assignment). Adopt that prompt as your operating instructions and do the work.

Agency does not execute tasks. There is no execution pipeline, no completion tracking, no state machine. The requester does the work.

### Step 3: Get evaluator

Call `agency_evaluator` with the `agency_task_id`. Agency returns:
- **`evaluator_prompt`** — instructions for evaluating the task output
- **`callback_jwt`** — single-use token authorising the evaluation submission (24-hour expiry)

### Step 4: Evaluate

Follow the `evaluator_prompt` to assess the output you produced in Step 2. Write your evaluation as text.

### Step 5: Submit evaluation

Call `agency_submit_evaluation` with:
- `agency_task_id` — the task being evaluated
- `callback_jwt` — from Step 3 (single-use)
- `output` — your evaluation text

Optional structured fields:
- `score` (integer 0–100) — numeric assessment
- `task_completed` (boolean) — whether the task was fully completed
- `score_type` — how to interpret the score: `binary`, `rubric`, `likert`, or `percentage`

Agency records the evaluation against the specific primitive composition that produced the agent. This builds the performance data that drives future composition improvements.

## Key rules

1. **Agency composes, you execute.** Do not wait for Agency to run the task.
2. **Use `agency_task_id`, not `external_id`.** The assign response includes an `agency_task_id_note` reminder.
3. **Complete the full loop.** Skipping evaluation means Agency learns nothing from the deployment.
4. **Each callback JWT is single-use.** If you need to resubmit, call `agency_evaluator` again for a fresh JWT.
5. **`next_step` guides you.** Every response includes a `next_step` field with plain-language instructions for what to do next.

## Project resolution

When `agency_assign` is called without an explicit `project_id`, it resolves in order:
1. `.agency-project` file in the requester's working directory
2. `AGENCY_PROJECT_ID` environment variable
3. `[project] default_id` in `agency.toml`

## Error format

All errors include:
```json
{
  "status": "error",
  "code": "<HTTP status or null>",
  "message": "<what went wrong>",
  "cause": "<most likely reason>",
  "fix": "<exact command or action to resolve>"
}
```

## Tool reference

For complete tool parameters and response schemas, see [using agency as an MCP with claude code](using%20agency%20as%20an%20MCP%20with%20claude%20code.md).
