# Agency + Superpowers Integration

Agency registers as a local MCP server in Claude Code, making its tools available natively during planning and task dispatch. This document covers setup, the three tools, response format, and common usage patterns.

## Prerequisites

- Agency v1.2.0 or later installed (`pip install agency-engine`)
- `agency init` completed (Phase 1 and Phase 2)
- `agency serve` running
- A valid MCP token at `~/.agency-mcp-token`

If you ran `agency init` through both phases, all of these are already in place.

## Setup

### Automatic (recommended)

During `agency init` Phase 1 Step 1.6, the wizard offers to register Agency as an MCP server in `~/.claude.json`. If you accepted, setup is complete.

### Manual

Add the following to `~/.claude.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "agency": {
      "command": "agency",
      "args": ["mcp"],
      "env": {
        "AGENCY_TOKEN_FILE": "/Users/you/.agency-mcp-token"
      }
    }
  }
}
```

`AGENCY_TOKEN_FILE` must be an absolute path. Do not use `~`.

To update the registration after changing server settings:

```bash
agency client setup
```

The setup wizard offers to update the MCP registration at the end.

## Response envelope

All three tools return JSON with a status envelope. Check `status` before accessing any other fields.

### Success

```json
{
  "status": "ok",
  ...additional fields specific to the tool
}
```

### Error

```json
{
  "status": "error",
  "code": 404,
  "message": "task not found"
}
```

`code` is the HTTP status code from the Agency server, or `null` if the error occurred before any HTTP call (e.g. no project configured, server unreachable).

## Tools

### `agency_assign`

Assign one or more tasks to AI agents. Agency composes agent descriptions from its primitive store and returns rendered prompts.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project_id` | string | No | Project UUID. If omitted, resolves from `AGENCY_PROJECT_ID` env var, then `[project] default_id` in `agency.toml`. |
| `tasks` | array | Yes | List of task objects (see below). |

Each task object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `external_id` | string | Yes | Your identifier for this task (e.g. a ticket ID). |
| `description` | string | Yes | What the agent should do. |
| `skills` | array of strings | No | Desired skills or capabilities. |
| `deliverables` | array of strings | No | Expected outputs. |

**Success response:**

```json
{
  "status": "ok",
  "assignment": {
    "assignments": [
      {
        "task_id": "...",
        "external_id": "...",
        "agent_prompt": "...",
        "evaluator_prompt": "...",
        "permission_block": "..."
      }
    ]
  }
}
```

Access the list of task assignments at `assignment.assignments`. Each entry contains the rendered agent prompt, the evaluator prompt, and the permission block.

**Error when no project is configured:**

```json
{
  "status": "error",
  "code": null,
  "message": "No project ID: pass project_id, set AGENCY_PROJECT_ID, or configure [project] default_id in agency.toml"
}
```

### `agency_evaluator`

Get the evaluator prompt and a callback JWT for a task that has been completed. The evaluator prompt tells the evaluating agent how to assess the work. The callback JWT authorises the evaluation submission.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `agency_task_id` | string | Yes | The Agency task ID (from `agency_assign` response). |

**Success response:**

```json
{
  "status": "ok",
  "evaluator_prompt": "You are evaluating the output of...",
  "callback_jwt": "eyJ..."
}
```

**Error responses:**

- `code: 404` — task not found
- `code: 422` — task has no evaluator assigned

### `agency_submit_evaluation`

Submit the evaluation output for a completed task. The submission includes content hash verification to confirm transmission integrity.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `agency_task_id` | string | Yes | The Agency task ID. |
| `callback_jwt` | string | Yes | The callback JWT from `agency_evaluator`. |
| `output` | string | Yes | The evaluation output text. |

**Success response:**

```json
{
  "status": "ok",
  "content_hash": "a1b2c3d4..."
}
```

`content_hash` is the SHA-256 hex digest of the submitted output as received by the server. If you need transmission integrity confirmation, compute the hash locally and compare. A mismatch means the content was altered in transit — retry the submission.

**Hash mismatch error:**

```json
{
  "status": "error",
  "code": null,
  "message": "Content hash mismatch: local=... server=..."
}
```

This error fires automatically if the server-reported hash does not match the locally computed hash. Retry the submission.

## Typical workflow

The three tools form a pipeline: assign, evaluate, submit.

1. **Assign tasks** using `agency_assign`. You get back rendered agent prompts for each task.
2. **Execute the tasks** using the agent prompts (this happens outside Agency — in Claude Code, Workgraph, or any other task runner).
3. **Get the evaluator** using `agency_evaluator` with the task ID from step 1.
4. **Run the evaluation** using the evaluator prompt returned in step 3.
5. **Submit the evaluation** using `agency_submit_evaluation` with the callback JWT from step 3 and the evaluation output from step 4.

## Project ID resolution

When `agency_assign` is called without an explicit `project_id`, it resolves the project in this order:

1. `AGENCY_PROJECT_ID` environment variable
2. `[project] default_id` in `agency.toml`
3. Error (no project configured)

The resolution happens at call time — `agency.toml` is re-read on every call. If you change the default project while the MCP server is running, the next `agency_assign` call picks up the change without restarting.

## Token management

The MCP server reads its authentication token from the file at `AGENCY_TOKEN_FILE` (default: `~/.agency-mcp-token`). This token is created during `agency init` Phase 2 Step 2.5, or manually:

```bash
agency token create --client-id mcp > ~/.agency-mcp-token
```

To list or revoke tokens:

```bash
agency token list
agency token revoke --client-id mcp
```

If you rotate the signing keypair (via `agency client setup`), all existing tokens are invalidated. Recreate them:

```bash
agency token create --client-id mcp > ~/.agency-mcp-token
```

## Troubleshooting

**"Agency server not reachable"** — The MCP server checks `GET /health` at startup. Make sure `agency serve` is running.

**"token file not found"** — Create a token: `agency token create --client-id mcp > ~/.agency-mcp-token`

**"No project ID"** — Either pass `project_id` explicitly, set `AGENCY_PROJECT_ID`, or create a default project: `agency project create`

**Tools not appearing in Claude Code** — Check that `~/.claude.json` has the `agency` entry under `mcpServers`. Run `agency client setup` and accept the MCP registration update.
