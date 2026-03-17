# Agency Caller Protocol

This document defines the contract between Agency (the agent composer) and the requester (the system that executes tasks). Agency composes agents; the requester executes them. The requester is responsible for the full assign → execute → evaluate loop.

## Terminology

- **Agency** — the composition service. Selects primitives, composes agents, records evaluations.
- **Requester** — the system calling Agency's tools. Executes tasks using returned prompts. In Claude Code, the requester is the LLM session via MCP tools. In CLI mode, the requester is a subagent or shell script calling `agency task` commands. In Workgraph, the requester is a shell script calling the HTTP API.

## Requester types

| Type | Interface | Token | Primary use |
|---|---|---|---|
| MCP (Claude Code) | MCP tools via stdio | `~/.agency-mcp-token` | Interactive Claude Code sessions |
| CLI | `agency task {assign,evaluator,submit,get}` | `~/.agency-cli-token` | Subagents, scripts, automation |
| Superpowers | MCP tools + skill orchestration | `~/.agency-superpowers-token` | Multi-step planning workflows |
| Workgraph | HTTP API via shell scripts | `~/.agency-workgraph-token` | Batch execution pipelines |

## The loop

### Step 1: Assign

**MCP:** Call `agency_assign` with one or more tasks.
**CLI:** `agency task assign --tasks '<json>' [--project-id <uuid>]`

Each task needs an `external_id` (your identifier) and a `description` (what the task requires).

Agency returns:
- **`status`** — `"ok"` on success
- **`task_ids`** — compact array of `{external_id, agency_task_id, agent_hash}` per task
- **`assignments`** — maps each `external_id` to an `agency_task_id` and `agent_hash`
- **`agents`** — maps each `agent_hash` to a `rendered_prompt` (the composed agent)

The `agency_task_id` is Agency's identifier for the task. Use it (not your `external_id`) in all subsequent calls.

**CLI task input:** exactly one of `--tasks` (inline JSON), `--tasks-file` (path), or `--tasks-stdin` (piped input).

### Step 2: Execute

For each task, read the `rendered_prompt` from the `agents` map (using the `agent_hash` from the assignment). Adopt that prompt as your operating instructions and do the work.

Agency does not execute tasks. There is no execution pipeline, no completion tracking, no state machine. The requester does the work.

### Step 3: Get evaluator

**MCP:** Call `agency_evaluator` with the `agency_task_id`.
**CLI:** `agency task evaluator --task-id <uuid> [--save-jwt <path>]`

Agency returns:
- **`evaluator_prompt`** — instructions for evaluating the task output
- **`callback_jwt`** — single-use token authorising the evaluation submission (24-hour expiry)
- **`agency_task_id`** — echoed back for convenience

The `--save-jwt` flag writes the JWT to a file for use by `--callback-jwt-file` on the submit step.

### Step 4: Evaluate

Follow the `evaluator_prompt` to assess the output you produced in Step 2. Write your evaluation as text.

### Step 5: Submit evaluation

**MCP:** Call `agency_submit_evaluation` with `agency_task_id`, `callback_jwt`, and `output`.
**CLI:** `agency task submit --task-id <uuid> --callback-jwt <jwt> --output <text>`

Optional structured fields:
- `score` (integer 0–100) — numeric assessment
- `task_completed` (boolean) — whether the task was fully completed
- `score_type` — how to interpret the score: `binary`, `rubric`, `likert`, or `percentage`

Agency records the evaluation against the specific primitive composition that produced the agent. This builds the performance data that drives future composition improvements.

### Error recovery: Get task

**MCP:** Call `agency_get_task` with the `agency_task_id`.
**CLI:** `agency task get --task-id <uuid>`

Returns the full task record: state, agent composition, rendered prompt, and evaluation status. Use this to resume after an interrupted loop or to check task state.

## Key rules

1. **Agency composes, you execute.** Do not wait for Agency to run the task.
2. **Use `agency_task_id`, not `external_id`.** The assign response includes an `agency_task_id_note` reminder (MCP) and a `task_ids` summary block (both).
3. **Complete the full loop.** Skipping evaluation means Agency learns nothing from the deployment.
4. **Each callback JWT is single-use.** If you need to resubmit, call `agency_evaluator` again for a fresh JWT.
5. **`next_step` guides you.** Every response includes a `next_step` field with plain-language instructions for what to do next. CLI: strip with `--no-guidance`.

## Client identity resolution

The `--client-id` flag determines which token file is read:

1. `--client-id` flag (CLI only)
2. `AGENCY_CLIENT_ID` environment variable
3. Default: `"cli"` for CLI commands, `"mcp"` for MCP tools

Token file path: `~/.agency-{client_id}-token` (special case: `mcp` respects `AGENCY_TOKEN_FILE` env var).

## Project resolution

When assigning without an explicit `project_id`, resolution order:
1. `.agency-project` file in the requester's working directory
2. `AGENCY_PROJECT_ID` environment variable
3. `[project] default_id` in `agency.toml`

## Error format

All errors include:
```json
{
  "status": "error",
  "error_type": "transient | auth | not_found | validation | permanent",
  "code": "<HTTP status or null>",
  "message": "<what went wrong>",
  "cause": "<most likely reason>",
  "fix": "<exact command or action to resolve>"
}
```

The `error_type` field is machine-actionable:
- `transient` — retry after delay (connection error, timeout, 503)
- `auth` — fix credentials (token file missing, 401)
- `not_found` — check IDs (404)
- `validation` — fix input (bad JSON, missing fields, 400/422/409)
- `permanent` — investigate (unexpected errors)

**CLI exit codes:** 0 success, 1 client error (fixable input), 2 server error (retry), 3 application error (check `error_type`).

## Tool reference

For complete MCP tool parameters and response schemas, see [using agency as an MCP with claude code](using%20agency%20as%20an%20MCP%20with%20claude%20code.md).

For CLI command reference: `agency task --help`, `agency task assign --help`, etc.
