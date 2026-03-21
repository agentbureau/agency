# Agency + Claude Code MCP Integration

Agency registers as a local MCP server in Claude Code, making its tools available natively during planning and task dispatch. This document covers setup, the eight tools, response formats, and the requester protocol.

## Prerequisites

- Agency v1.2.1 or later installed (`pipx install agency-engine`)
- `agency init` completed (Phase 1 and Phase 2)
- `agency serve` running
- A valid MCP token at `~/.agency-mcp-token`

If you ran `agency init` through both phases, all of these are already in place.

## Setup

### Automatic (recommended)

During `agency init` Phase 1 Step 1.6, the wizard registers Agency as an MCP server in `~/.claude.json` using the absolute path to the `agency` binary. If you accepted, setup is complete.

### Manual

Add the following to `~/.claude.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "agency": {
      "command": "/absolute/path/to/agency",
      "args": ["mcp"],
      "env": {
        "AGENCY_TOKEN_FILE": "~/.agency-mcp-token"
      }
    }
  }
}
```

Both `command` and `AGENCY_TOKEN_FILE` must be absolute paths. Do not use `~`.

To find the absolute path: `which agency`

## Response format

### Success

Each tool returns its own response shape (see tool documentation below). All successful responses include a `next_step` field with plain-language instructions for what to do next.

### Error

All error responses use a standard envelope:

```json
{
  "status": "error",
  "code": 404,
  "message": "Task not found for agency_task_id: {id}.",
  "cause": "The ID does not match any task. Most common mistake: passing your external_id instead of the agency_task_id returned by agency_assign.",
  "fix": "Check the agency_assign response — use the agency_task_id field, not external_id."
}
```

- `code` — HTTP status code, or `null` if the error occurred before any HTTP call
- `message` — what went wrong
- `cause` — most likely reason
- `fix` — exact command or action to resolve

## Tools

### `agency_assign`

Compose AI agents for a set of tasks and return their prompts. Agency is a prompt composer — it does not execute tasks. The requester must execute each task using the returned `rendered_prompt`.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project_id` | string | No | Project UUID. Resolves from: `.agency-project` > `AGENCY_PROJECT_ID` env > `agency.toml [project] default_id` |
| `tasks` | array | Yes | At least one task object |

Each task object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `external_id` | string | Yes | Your identifier for this task |
| `description` | string | Yes | What the task requires. Agency uses this to select primitives and compose the agent. |
| `skills` | array of strings | No | Skill tags to influence primitive selection |
| `deliverables` | array of strings | No | Expected outputs |

**Response:**

```json
{
  "assignments": {
    "<external_id>": {
      "agency_task_id": "uuid-v7",
      "agency_task_id_note": "Use this agency_task_id (not your external_id) when calling agency_evaluator and agency_submit_evaluation.",
      "agent_hash": "sha256-hex"
    }
  },
  "agents": {
    "<agent_hash>": {
      "rendered_prompt": "string",
      "content_hash": "string",
      "template_id": "string",
      "primitive_ids": { "role_components": [], "desired_outcomes": [], "trade_off_configs": [] }
    }
  },
  "next_step": "You must now execute each task yourself..."
}
```

Use `agent_hash` from the assignment to look up the `rendered_prompt` in the `agents` map.

### `agency_evaluator`

Get the evaluator prompt and callback JWT for a completed task.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `agency_task_id` | string | Yes | The `agency_task_id` from `agency_assign` (not your `external_id`) |

**Response:**

```json
{
  "evaluator_prompt": "string",
  "callback_jwt": "string",
  "agency_task_id": "string",
  "next_step": "Evaluate the output you produced for this task..."
}
```

The `evaluator_prompt` tells you how to evaluate. The `callback_jwt` is single-use (24h expiry) and authorises the evaluation submission.

### `agency_submit_evaluation`

Submit your evaluation of a completed task.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `agency_task_id` | string | Yes | The `agency_task_id` from `agency_assign` |
| `callback_jwt` | string | Yes | The `callback_jwt` from `agency_evaluator`. Single-use. |
| `output` | string | Yes | Your evaluation text |
| `score` | integer | No | Numeric score (0–100) |
| `task_completed` | boolean | No | Whether the task was fully completed |
| `score_type` | string | No | How to interpret the score: `binary`, `rubric`, `likert`, or `percentage` |

**Response:**

```json
{
  "status": "ok",
  "content_hash": "sha256-hex",
  "next_step": "Evaluation recorded. The assign-execute-evaluate loop for this task is complete."
}
```

### `agency_list_projects`

List all projects in this Agency instance.

**Parameters:** None.

**Response:**

```json
{
  "projects": [
    { "id": "uuid", "name": "string", "description": "string or null", "is_default": true, "created_at": "ISO-8601" }
  ],
  "default_project_id": "uuid or null",
  "default_source": "repo_config | env_var | toml_config | none",
  "next_step": "Pass a project_id to agency_assign, or omit it to use the default project."
}
```

`default_source` tells you how the default was resolved.

### `agency_create_project`

Create a new Agency project.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | Yes | Project name (1–255 characters) |
| `description` | string | No | Project description |
| `contact_email` | string | No | Contact email for agent prompts |
| `oversight_preference` | string | No | `discretion` or `review` |
| `error_notification_timeout` | integer | No | Timeout in seconds |
| `attribution` | boolean | No | Agent output attribution |
| `set_as_default` | boolean | No | Set as default in agency.toml |

**Response:**

```json
{
  "project_id": "uuid",
  "name": "string",
  "is_default": true,
  "settings_applied": { ... },
  "next_step": "This project is now available for task assignment..."
}
```

Omitted settings inherit from instance defaults.

### `agency_get_task`

Retrieve full task state, composition, and evaluation status.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `agency_task_id` | string | Yes | The `agency_task_id` from `agency_assign` |

**Response:**

```json
{
  "agency_task_id": "uuid",
  "state": "assigned | evaluation_pending | evaluation_received",
  "agent_hash": "sha256-hex",
  "rendered_prompt": "string",
  "evaluation": null,
  "next_step": "..."
}
```

`state` is derived at query time. `evaluation` is null until an evaluation is submitted, then contains the full evaluation record.

### `agency_status`

Get instance status: projects, active tasks, task progress, and primitive store health.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project_id` | string | No | Filter to a single project |

**Response:**

```json
{
  "instance_id": "uuid",
  "server_version": "1.2.1",
  "uptime_seconds": 3600,
  "projects": [
    {
      "id": "uuid", "name": "string", "is_default": true,
      "task_summary": { "total": 10, "assigned": 3, "evaluation_pending": 2, "evaluation_received": 5 },
      "active_tasks": [ { "agency_task_id": "uuid", "state": "assigned", ... } ]
    }
  ],
  "primitive_counts": { "role_components": 150, "desired_outcomes": 80, "trade_off_configs": 40, "eligible": 200 },
  "next_step": "..."
}
```

The `next_step` is context-sensitive — it tells you about assigned tasks needing evaluation if any exist.

### `agency_triage`

Lightweight, stateless primitive matching without full composition. Use to check whether Agency has relevant primitives for a task before paying the cost of full composition.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `description` | string | Yes | Task description to match against |

**Response:**

```json
{
  "matched_primitives": [
    { "name": "string", "type": "role_component|desired_outcome|trade_off_config", "similarity": 0.0 }
  ],
  "recommendation": "compose | skip-safe",
  "reasoning": "string"
}
```

`recommendation` indicates whether full composition is likely to add value for this task.

## Requester protocol

The full assign → execute → evaluate loop:

1. **`agency_assign`** — compose agents for your tasks, receive rendered prompts
2. **Execute** — adopt each `rendered_prompt` as your operating instructions and do the work (Agency does not execute)
3. **`agency_evaluator`** — get evaluation criteria and callback JWT for each completed task
4. **Evaluate** — follow the `evaluator_prompt` to assess your own output
5. **`agency_submit_evaluation`** — submit evaluation text, optionally with score and completion status

Full protocol documentation: [caller-protocol.md](caller-protocol.md)

> **Terminology note:** "requester" refers to any task manager or human that calls Agency from outside to compose and receive agents. Internal server-side operations within Agency are not requester calls.

## Project ID resolution

When `agency_assign` is called without an explicit `project_id`, it resolves in this order:

1. `.agency-project` file in the requester's working directory (or parent directories)
2. `AGENCY_PROJECT_ID` environment variable
3. `[project] default_id` in `agency.toml`

Resolution happens at call time — changes take effect without restarting the MCP server.

To pin a project to a repo: `agency project pin --project-id <uuid>`

## Token management

The MCP server reads its bearer token from `AGENCY_TOKEN_FILE` (default: `~/.agency-mcp-token`).

```bash
# Create
agency token create --client-id mcp > ~/.agency-mcp-token

# Revoke
agency token revoke --client-id mcp

# Recreate after keypair rotation
agency token create --client-id mcp > ~/.agency-mcp-token
```

## Troubleshooting

**"Cannot reach Agency server"** — `agency serve` is not running. The MCP server continues operating after a failed health check and retries each tool call once (2s delay).

**"MCP token file not found"** — Create a token: `agency token create --client-id mcp > ~/.agency-mcp-token`

**"No project ID provided"** — Create a `.agency-project` file (`agency project pin`), set `AGENCY_PROJECT_ID`, or configure a default project.

**"Callback JWT is invalid, expired, or already used"** — Each callback JWT is single-use with a 24-hour expiry. Call `agency_evaluator` again to get a fresh one.

**Tools not appearing in Claude Code** — Check that `~/.claude.json` has the `agency` entry under `mcpServers` with an absolute path. Run `agency init` to re-register.
