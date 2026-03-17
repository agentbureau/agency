# Agency + Workgraph Integration

Agency integrates with Workgraph via shell-based translators that batch-assign open tasks, store rendered prompts locally, and run the full assign-execute-evaluate loop per task. Unlike the MCP/Superpowers integration (which operates inside Claude Code), the Workgraph integration runs as standalone shell scripts that call the Agency API directly.

## Prerequisites

- Agency v1.2.2 or later installed (`pipx install agency-engine`)
- `agency init` completed (Phase 1 and Phase 2)
- `agency serve` running
- A valid Workgraph token at `~/.agency-workgraph-token`
- Workgraph CLI (`wg`) installed and configured

Create the token:

```bash
agency token create --client-id workgraph > ~/.agency-workgraph-token
```

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AGENCY_PROJECT_ID` | Yes | — | Project UUID for task assignment |
| `AGENCY_STATE_DIR` | No | `~/.agency` | Agency configuration directory |
| `AGENCY_TOKEN_FILE` | No | `~/.agency-workgraph-token` | Path to bearer token file |
| `WG_MODEL` | No | `claude-sonnet-4-6` | Model for Claude CLI execution |
| `WG_TASK_ID` | Set by Workgraph | — | Current task ID (set by executor runtime) |
| `WG_AGENT_ID` | Set by Workgraph | — | Current agent ID (set by executor runtime) |

## Components

### `agency-assign-workgraph` — Batch assignment script

Collects all open Workgraph tasks, sends them to Agency's batch assign endpoint, stores rendered prompts and `agency_task_id` mappings locally, and sets the Agency executor on each assigned task.

**Usage:**

```bash
export AGENCY_PROJECT_ID="your-project-uuid"
./translators/workgraph/agency-assign-workgraph
```

**What it does:**

1. Reads Agency connection details from `agency.toml`
2. Lists all open Workgraph tasks (`wg list --status open --json`)
3. Builds a batch payload with `external_id`, `description`, `skills`, and `deliverables` per task
4. Calls `POST /projects/{project_id}/assign` on the Agency API
5. Stores each task's `rendered_prompt` to `.workgraph/agency-prompts/{task_id}.prompt`
6. Stores each task's `agency_task_id` to `.workgraph/agency-prompts/{task_id}.task_id`
7. Sets `agency-wg-executor.sh` as the executor for each assigned task

### `agency-wg-executor.sh` — Per-task executor

Runs as the Workgraph executor for each assigned task. Reads the stored prompt, executes it with Claude CLI, then runs the full evaluation loop.

**Lifecycle:**

1. Reads the rendered prompt from `.workgraph/agency-prompts/{WG_TASK_ID}.prompt`
2. Reads the `agency_task_id` from `.workgraph/agency-prompts/{WG_TASK_ID}.task_id`
3. Starts a heartbeat loop (every 90s) to prevent Workgraph from killing the agent
4. Runs `claude --print` with the rendered prompt
5. On success:
   - Marks the Workgraph task as done (`wg done`)
   - Fetches the evaluator prompt and callback JWT from `GET /tasks/{agency_task_id}/evaluator`
   - Runs the evaluator prompt with Claude CLI
   - Submits the evaluation output to `POST /tasks/{agency_task_id}/evaluation`
6. On failure:
   - Marks the Workgraph task as failed with the exit code

## Typical workflow

```bash
# 1. Start Agency
agency serve

# 2. Set your project
export AGENCY_PROJECT_ID="$(agency project list --format json | python3 -c 'import sys,json; print(json.load(sys.stdin)["projects"][0]["id"])')"

# 3. Batch-assign all open Workgraph tasks
./translators/workgraph/agency-assign-workgraph

# 4. Start the Workgraph service (executes assigned tasks)
wg service start
```

### Alternative: CLI-based executor (v1.2.2)

Instead of raw HTTP calls, executors can use the `agency task` CLI commands:

```bash
# Assign
RESULT=$(agency task assign --tasks-file tasks.json --client-id workgraph --format json)

# Extract task IDs
echo "$RESULT" | python3 -c 'import sys,json; [print(t["agency_task_id"]) for t in json.load(sys.stdin)["task_ids"]]'

# Get evaluator
agency task evaluator --task-id "$AGENCY_TASK_ID" --save-jwt /tmp/jwt.txt --client-id workgraph

# Submit evaluation
agency task submit --task-id "$AGENCY_TASK_ID" --callback-jwt-file /tmp/jwt.txt --output-file eval.txt --client-id workgraph
```

The CLI handles token resolution, error classification, and exit codes automatically.

## Differences from MCP/Superpowers integration

| | MCP (Superpowers) | CLI | Workgraph (HTTP) |
|---|---|---|---|
| **Transport** | MCP stdio (in-process) | Shell commands | HTTP API (shell scripts) |
| **Assignment** | Per-tool-call | Per-command | Batch (all open tasks) |
| **Execution** | Claude Code session | Subagent / script | `claude --print` subprocess |
| **Evaluation** | Same Claude Code session | Same script | Separate subprocess |
| **Token file** | `~/.agency-mcp-token` | `~/.agency-cli-token` | `~/.agency-workgraph-token` |
| **Prompt storage** | In-memory (MCP response) | stdout JSON | `.workgraph/agency-prompts/` on disk |

## Token management

```bash
# Create
agency token create --client-id workgraph > ~/.agency-workgraph-token

# Revoke
agency token revoke --client-id workgraph

# Recreate after keypair rotation
agency token create --client-id workgraph > ~/.agency-workgraph-token
```

## Troubleshooting

**"AGENCY_PROJECT_ID: parameter not set"** — Export the project ID before running the assign script: `export AGENCY_PROJECT_ID="your-uuid"`

**"Connection refused"** — `agency serve` is not running. Start it first.

**Heartbeat timeout** — The executor sends heartbeats every 90 seconds. If Claude CLI takes longer than the Workgraph timeout between heartbeats, increase the Workgraph agent timeout or reduce heartbeat interval in the executor script.

**Evaluator 404** — The executor passes `agency_task_id` (not `WG_TASK_ID`) to the evaluator endpoint. If the `.task_id` file is missing or corrupt, re-run `agency-assign-workgraph`.
