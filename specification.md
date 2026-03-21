# Agency — specification v1.2.3
*2026-03-22*

## Getting started

Install Agency, then run the setup wizard:

```bash
pipx install --python python3.13 agency-engine
agency init
```

Once setup completes, open Claude Code and use the skill `/agency-getting-started` for an interactive walkthrough of the Agency workflow: composing agents, executing tasks, and submitting evaluations.

---

## Purpose and scope

Agency is a standalone service for composing, assigning, evaluating, and evolving AI agents. It is released under Elastic License 2.0. This licence permits self-hosting for internal use without restriction. The one thing it does not permit is offering Agency as a managed or hosted service commercially. If you are running Agency for your own organisation's tasks, the licence does not affect you.

Agency does not execute tasks. It composes and assigns agent descriptions; the task manager executes tasks using those descriptions. Agency works with any task management system.

v1.2.0 adds native MCP integration for Claude Code, Ed25519 authentication, token management, the permission model, a two-phase setup wizard, instance/project configuration hierarchy, agent output attribution, primitive quality scores and distribution, and SMTP error notification.

v1.2.2 adds CLI task commands (`agency task {assign,evaluator,submit,get}`), a shared client module, a new `GET /tasks/{task_id}` API endpoint with re-rendering pipeline, the `agency_get_task` MCP tool, `error_type` in all error responses, `task_ids` summary block in assign responses, and `status: "ok"` across all success responses.

v1.2.3 adds metaprimitives (primitives that govern Agency's own functional agents), a triage endpoint (`POST /triage`), MCP auto-start for zero-terminal operation, non-interactive setup flags, first-run onboarding, setup wizard improvements, critical persistence bug fixes, and two new bundled skills (`agency-getting-started`, `agency-composition-config`).

---

## Core concepts

### Primitives

Agency stores three types of primitives independently:

- **Role components** — individual capabilities: the ability to do a specific thing
- **Desired outcomes** — what success looks like for a type of work
- **Trade-off configurations** — acceptable and unacceptable trade-offs governing how work is done

These are stored as independent, uncommitted objects. Pre-composed agents are a cache on top of this primitive store, not the ground truth.

Each primitive carries a quality score (integer, 0-100). The assigner only selects primitives with quality > 90 for new compositions. Quality scores are set at primitive creation time and updated by `agency primitives update` from the upstream starter CSV.

### Metaprimitives

A metaprimitive is a primitive that governs how Agency itself operates — as distinct from task primitives composed into requester-facing agents. Metaprimitives live in the same primitive tables as task primitives, distinguished by a `scope` column. Values: `task` (default), `meta:assigner`, `meta:evaluator`, `meta:evolver`, `meta:agent_creator`.

v1.2.3 ships 7 starter assigner metaprimitives.

### Composition config

`~/.agency/composition-rules.csv` governs how Agency's functional agents are composed. It is a watched file: changes take effect on the next composition call without server restart. Editable directly or via the `agency-composition-config` skill in Claude Code.

### Triage

A lightweight, stateless, read-only check (`POST /triage`) that returns the best-matching primitives for a task description without performing full composition. Used to decide whether composition adds value before paying its cost. See the Triage endpoint section under Integration surface.

### Agents and actor-agents

An **agent** is a composition of role components + desired outcomes + trade-off configuration. It is a deployable configuration that may exist in the composition cache without being assigned to any task.

An **actor-agent** is an agent that has been assigned to a specific task and is actively performing it.

### Self-similar system

All special-type agents — assigner, evaluator, evolver, agent creator — are first-class agents governed by the same primitive structure as every other agent. None are privileged system components. All accumulate performance history and are subject to selection pressure.

### Batch assignment

A single API call that accepts a complete set of task descriptions, composes an agent for each, deduplicates similar compositions, and returns a packet containing all assignments and all unique agent definitions. The requester stores this packet locally and does not need to call Agency again during execution.

This is the preferred integration pattern for task management tools. It replaces per-task calls during execution with a single pre-flight call before execution begins.

### MCP integration

Agency registers as a local MCP server in Claude Code. When registered, Claude Code calls Agency tools natively during planning and dispatch — without the user invoking a skill or writing shell commands. The MCP server translates tool calls into authenticated HTTP calls to the running `agency serve` process.

### Instance/project configuration hierarchy

Seven settings operate on a two-level hierarchy. The instance level (in `agency.toml`) sets the default for the entire installation. Individual projects can override any of these settings independently. A project that does not override a setting inherits the current instance value dynamically.

The seven hierarchical settings are: contact email, oversight preference, error notification timeout, attribution, LLM provider, LLM model, and LLM API key.

Resolution rule: the project column value is used if non-null; otherwise the instance value is used. A null project value means "use whatever the instance is currently set to." If the instance setting is later changed, all projects with null for that field inherit the new value automatically.

---

## Configuration

Agency stores all state in `~/.agency/`. The config file is `~/.agency/agency.toml`. It is generated by `agency init`.

### `agency.toml` structure

```toml
instance_id = "uuid-v7"

[server]
host = "127.0.0.1"
port = 8000

[llm]
backend = "claude-code"          # or "api" or "other"
endpoint = ""                    # only used if backend = "api" or "other"
model = "claude-sonnet-4-6"
api_key = ""                     # only used if backend = "api" or "other"

[notifications]
contact_email = "you@example.com"
error_notification_timeout = 1800
oversight_preference = "discretion"

[smtp]
host = "smtp.gmail.com"
port = 587
username = "you@gmail.com"
password = "app-password"
from_address = "you@gmail.com"

[output]
attribution = true

[project]
default_id = "uuid-v7"
```

The `[llm]` section supports three backends:
- `claude-code` — uses the `claude --print` CLI (user's existing Claude subscription; no API key required)
- `api` — direct Anthropic API call with API key
- `other` — any OpenAI-compatible endpoint (Ollama, LM Studio, other providers)

### Key storage

Ed25519 keypair stored as PEM files in `~/.agency/keys/`:

```
~/.agency/keys/agency.ed25519.pem      # private signing key (permissions 600)
~/.agency/keys/agency.ed25519.pub.pem  # public verification key (permissions 644)
```

Generated by `agency init` Phase 1.

---

## Authentication

Agency uses Ed25519 asymmetric signing (`EdDSA` algorithm) for all JWT tokens. The private key signs tokens; the public key verifies them. The public key can be distributed freely without compromising security.

### Task manager tokens

Issued via `agency token create`. JWT claims:

```json
{
  "jti": "<uuid-v7>",
  "client_id": "<string>",
  "instance_id": "<uuid-v7>",
  "scope": "task",
  "iat": "<unix-timestamp>"
}
```

Each token's `jti` is recorded in the `issued_tokens` table. The JWT middleware checks for revocation after signature verification: if the `jti` is present and `revoked = 1`, returns 401.

### Evaluator tokens

Generated by Agency at evaluator creation time and baked into the evaluator's rendered prompt. JWT claims additionally include `project_id`, `task_id`, and `exp`. Each JWT is task-scoped and single-use.

### Token management

```bash
agency token create --client-id <name>    # create and print to stdout
agency token list                          # table of all issued tokens
agency token revoke --client-id <name>     # revoke all tokens for a client
```

Revocation requires confirmation by typing: `yes, cancel every token, even ones on different computers`

### Compatibility with v1.1.0

v1.2.0 uses `EdDSA` instead of v1.1.0's `HS256`. All v1.1.0 tokens are immediately invalid after upgrading. Users must recreate tokens with `agency token create`.

---

## Agent output attribution

Every agent prompt rendered by Agency includes an instruction to append a standard attribution and disclosure note at the end of the output:

```
This output was produced by an AI agent configured via Agency — an engine for configuring and evolving teams of AI agents. Machine-readable: ai-generated=true agent-config=agency url=https://github.com/agentbureau/agency
```

Format by output type:

| Output format | Format |
|---|---|
| `prose`, `markdown`, or unset | HTML comment: `<!-- text -->` |
| `yaml` | YAML comment: `# text` |
| `json`, `code`, or any other value | Omitted |

Attribution is on by default. Overridable at instance level (`agency.toml [output] attribution`) and project level (`projects.attribution`), following the null-inherit hierarchy.

---

## Integration surface

### MCP server (`agency mcp`)

Transport: stdio. Launched by Claude Code as a subprocess. Requires `agency serve` to be running (started automatically via MCP auto-start if not already running — see Zero-terminal).

At startup, reads: Agency URL from `agency.toml`, JWT token from `AGENCY_TOKEN_FILE` (default: `~/.agency-mcp-token`), default project ID from `AGENCY_PROJECT_ID` env var or `agency.toml [project] default_id`.

Eight tools (v1.2.3):

#### `agency_assign`

```json
{
  "project_id": "string (optional — falls back to default)",
  "tasks": [
    {
      "external_id": "string",
      "description": "string",
      "skills": ["string"],
      "deliverables": ["string"]
    }
  ]
}
```

Calls `POST /projects/{project_id}/assign`. Returns the full assignment packet as JSON.

#### `agency_evaluator`

```json
{ "agency_task_id": "string" }
```

Calls `GET /tasks/{agency_task_id}/evaluator`. Returns `evaluator_prompt` and `callback_jwt`.

#### `agency_submit_evaluation`

```json
{
  "agency_task_id": "string",
  "callback_jwt": "string",
  "output": "string"
}
```

Calls `POST /tasks/{agency_task_id}/evaluation`. Returns `{"status": "ok", "content_hash": "<sha256>"}`. The requester should verify the returned content hash against the SHA-256 of the payload sent.

#### `agency_get_task` (v1.2.2)

```json
{ "agency_task_id": "string" }
```

Calls `GET /tasks/{agency_task_id}`. Returns full task record: state (assigned/evaluation_pending/evaluation_received), agent_hash, re-rendered prompt, rendering warnings, and evaluation sub-object (null or full).

#### `agency_list_projects` (v1.2.1)

No parameters. Calls `GET /projects`. Returns list of projects with default identification.

#### `agency_create_project` (v1.2.1)

```json
{ "name": "string", "description": "string (optional)", "set_as_default": "boolean (optional)" }
```

Calls `POST /projects`. Returns project_id and settings_applied.

#### `agency_status` (v1.2.1)

```json
{ "project_id": "string (optional)" }
```

Calls `GET /status`. Returns instance status, per-project task summaries, and primitive counts.

#### `agency_triage` (v1.2.3)

```json
{ "description": "string" }
```

Calls `POST /triage`. Returns best-matching primitives, recommendation (`compose` or `skip-safe`), and reasoning. See Triage endpoint below.

### Triage endpoint (v1.2.3)

`POST /triage` — lightweight, stateless, read-only primitive matching. Skips template selection, prompt rendering, composition caching, and task creation.

**Request:**

```json
{
  "description": "string (required)",
  "project_id": "string (optional — reserved for future project-specific pools)"
}
```

**Response:**

```json
{
  "matched_primitives": [
    { "name": "string", "type": "role_component|desired_outcome|trade_off_config", "similarity": 0.0 }
  ],
  "recommendation": "compose|skip-safe",
  "reasoning": "string"
}
```

### CLI task commands (v1.2.2)

Four non-interactive commands mirroring the MCP task tools. All call the shared client module (`agency/client.py`).

```bash
agency task assign   --tasks '<json>' [--tasks-file <path>] [--tasks-stdin] [--project-id <uuid>]
agency task evaluator --task-id <uuid> [--save-jwt <path>]
agency task submit   --task-id <uuid> --callback-jwt <jwt> --output <text> [--score 0-100]
agency task get      --task-id <uuid>
```

Shared flags: `--client-id` (default `cli`), `--timeout` (default 30), `--format json|table`, `--no-guidance`, `--quiet/-q`.

Exit codes: 0 success, 1 client error, 2 server error, 3 application error.

### Error response schema (v1.2.2)

All error responses include six fields:

```json
{
  "status": "error",
  "error_type": "transient | auth | not_found | validation | permanent",
  "code": 404,
  "message": "Task not found.",
  "cause": "The agency_task_id does not match any task.",
  "fix": "Check the agency_task_id from the assign response."
}
```

### Project level

| Direction | Signal | Notes |
|---|---|---|
| IN | Project definition with all settings | `POST /projects` or `agency project create` |
| IN | LLM credentials (instance or project override) | Set at init time or project creation |
| IN | Oversight preference | `discretion` or `review`; null inherits instance default |
| IN | Error notification timeout | Seconds; null inherits instance default |
| IN | Contact email | Null inherits instance default |
| IN | Attribution preference | On/off; null inherits instance default |
| IN | Permission block | 13-character default for all entities in project |
| OUT | Project ID + confirmation | UUID v7 |

### Task level — individual

| Direction | Signal | Notes |
|---|---|---|
| IN | Task description + project ID | `POST /tasks` |
| OUT | Task agent (markdown) | `GET /tasks/{id}/agent` |
| OUT | Evaluator agent (markdown) | `GET /tasks/{id}/evaluator` — callback JWT baked in |
| IN | Evaluation report | `POST /tasks/{id}/evaluation` |

### Task level — batch

| Direction | Signal | Notes |
|---|---|---|
| IN | List of task descriptions + project ID | `POST /projects/{id}/assign` |
| OUT | Assignment packet | Task-to-agent mapping + deduplicated agent definitions |

The batch endpoint is the preferred integration pattern. The requester sends all tasks at once before execution begins. Agency returns a packet mapping each task to a composed agent and including all unique agent definitions. Tasks that compose to similar agents (cosine similarity >= 0.90) share a single agent definition.

**Request body:**

```json
{
  "tasks": [
    {
      "external_id": "string",
      "description": "string",
      "skills": ["string"],
      "deliverables": ["string"]
    }
  ]
}
```

**Response:**

```json
{
  "status": "ok",
  "task_ids": [
    {"external_id": "string", "agency_task_id": "uuid-v7", "agent_hash": "sha256-hex"}
  ],
  "assignments": {
    "<external_id>": {
      "agency_task_id": "uuid-v7",
      "agent_hash": "sha256-hex"
    }
  },
  "agents": {
    "<agent_hash>": {
      "rendered_prompt": "string",
      "content_hash": "string",
      "template_id": "string",
      "permission_block": "string",
      "primitive_ids": {
        "role_components": ["uuid"],
        "desired_outcomes": ["uuid"],
        "trade_off_configs": ["uuid"]
      }
    }
  }
}
```

The `agents` map is deduplicated. If the primitive store is empty, the endpoint returns `503` with `{"error": "primitive_store_empty"}`.

### Callbacks from field (evaluator -> Agency)

| Direction | Signal |
|---|---|
| IN | Full evaluation report — `POST /tasks/{id}/evaluation` |

The endpoint computes SHA-256 of the received payload and returns `{"status": "ok", "content_hash": "<sha256>"}`. The requester verifies the returned hash against the hash of what was sent. Duplicate submissions (same `jti` + `task_id`) are rejected with 401.

### Evolution oversight

| Direction | Signal |
|---|---|
| OUT | Evolution proposal (changes requiring human sign-off) |
| IN | Human approval/rejection |

### Admin

| Direction | Signal |
|---|---|
| IN | Primitive ingestion — `POST /primitives` (single) or `POST /primitives/import` (CSV) |

---

## Primitive distribution

The starter primitive set is hosted as a CSV file in the public Agency GitHub repository and fetched at init time. It is not bundled in the pip package.

**CSV columns:** `type`, `name`, `description`, `quality`, `domain_specificity`, `domain`, `scope`, `origin_instance_id`, `parent_content_hash`.

### `agency primitives update`

```bash
agency primitives update
```

Fetches the current starter CSV and reconciles with the local store:

1. **New primitives** (content hash not in local store, quality > 90): inserted with all CSV fields including `scope`
2. **Existing primitives with changed quality, domain_specificity, or domain**: local columns updated; one row written to `primitive_mutations` per changed field
3. **Unchanged primitives**: no action
4. **Local primitives not in upstream CSV**: no action (may be locally created)
5. **`parent_content_hash`**: stored on ingest for new primitives; immutable once set

Quality threshold is hardcoded at > 90 in v1.2.0.

---

## Setup and CLI

### `agency init` — two-phase setup wizard

Covers the full installation lifecycle. Every step checks whether it has already been completed and skips if so. Safe to re-run at any time. Uses a three-layer typography system: (1) system status lines (dim, checkmark/cross prefix), (2) helper/explanation text (italic, indented), (3) user prompts (bold, cyan accent, `▶` prefix). Falls back to plain text when stdout is not a TTY.

Supports `--non-interactive` mode: when any flag is passed on the command line, the wizard runs without prompts, using flag values and defaults. This enables zero-terminal setup from within Claude Code.

**Phase 1 — Configuration (5 steps, no server required):**

| Step | What | Input |
|---|---|---|
| 1.1 | Generate instance credentials (UUID v7, Ed25519 keypair) | Automatic |
| 1.2 | Configure server settings (host, port) | Automatic |
| 1.3 | Configure LLM connection | User selects backend and provides credentials |
| 1.4 | Configure notifications (contact email, timeout, oversight, SMTP) | User input |
| 1.5 | Configure output defaults (attribution) | User input |

**Phase 2 — Initialisation (7 steps, runs the server briefly):**

| Step | What | Input |
|---|---|---|
| 2.1 | Initialise database (start server, run migrations, stop) | Automatic |
| 2.2 | Download embedding model (`all-MiniLM-L6-v2`, ~80MB) | Automatic |
| 2.3 | Install starter primitives (fetch CSV from GitHub — auto-download on first install) | Automatic |
| 2.4 | Create first project (runs project creation wizard) | User input |
| 2.5 | Create integration tokens (MCP, CLI, Superpowers, Workgraph) | Automatic |
| 2.6 | Register with Claude Code (MCP server in `~/.claude.json`) | User confirms |
| 2.7 | Install Claude Code skills | Automatic |

### `agency client setup`

```bash
agency client setup
```

Reviews and updates instance-level settings. Shows the current value of every setting; press enter to keep or type a new value to change. Includes protective behaviours for high-impact changes: keypair rotation requires typed confirmation and revokes all tokens; LLM changes run a connection test; contact email changes note which projects inherit. Supports `--non-interactive` mode via flags.

### `agency project create`

```bash
agency project create
```

Interactive wizard to create a new project. Prompts for name and all project-level settings. Press enter to inherit the instance default (stored as null). After creation, offers to set as the default project.

### `agency skills install`

```bash
agency skills install
```

Installs bundled Claude Code skills into `~/.claude/skills/`. Idempotent — updates any skill whose content hash differs from the bundled version.

Bundled skills in v1.2.3:
- `agency-primitive-extraction` — guides Claude through extracting and authoring Agency primitives from existing prompts and agent descriptions
- `agency-getting-started` — interactive walkthrough of the Agency workflow (assign → execute → evaluate), primitives explanation, and optional CLAUDE.md configuration
- `agency-composition-config` — guided editing of `~/.agency/composition-rules.csv` via Claude Code conversation

### Token commands

```bash
agency token create --client-id <name>    # create, print to stdout
agency token list                          # table of all issued tokens
agency token revoke --client-id <name>     # revoke all tokens for a client
```

---

## Zero-terminal

Agency supports fully zero-terminal operation: all setup, configuration, and serving can run inside Claude Code without requiring a separate terminal window.

### MCP auto-start

When the MCP server starts (`agency mcp`), it checks whether `agency serve` is reachable. If not, it spawns `agency serve` as a background subprocess and polls the `/health` endpoint until the server is ready or timeout (30s). The server process is registered for cleanup on MCP process exit (`atexit`). If `agency serve` is already running, no action is taken.

### Non-interactive flags

`agency init` and `agency client setup` accept command-line flags for all configuration values. When any flag is provided, the wizard runs non-interactively using flag values and sensible defaults. This allows Claude Code to run setup without interactive stdin.

---

## First-run onboarding

On the first successful `agency_assign` or `agency_status` MCP tool call, Agency injects a `first_run_onboarding` field into the response:

```json
{
  "first_run_onboarding": {
    "message": "Agency is set up and working. Would you like a quick walkthrough of how to use it?",
    "skill_name": "agency-getting-started",
    "skip_instruction": "To skip, just proceed with your task. This message won't appear again."
  }
}
```

The field is injected in the MCP layer, not the API layer. Detection uses a marker file (`~/.agency/.onboarded`): absent = first run (inject and create marker), present = skip. The field appears once per instance lifetime.

The `agency-getting-started` skill is also invocable at any time via `/agency-getting-started`.

---

## Translators

Translators connect task management tools to Agency.

### MCP (Claude Code)

The primary integration for Claude Code. `agency mcp` runs as an MCP server over stdio. See the MCP server section above for tool definitions.

**One-time setup:**

Handled by `agency init` Phase 1 Step 1.6 and Phase 2 Step 2.5. Manual setup if needed:

```bash
agency token create --client-id mcp > ~/.agency-mcp-token
```

Then merge into `~/.claude.json`:

```json
{
  "mcpServers": {
    "agency": {
      "command": "agency",
      "args": ["mcp"],
      "env": {
        "AGENCY_TOKEN_FILE": "~/.agency-mcp-token"
      }
    }
  }
}
```

### Workgraph (`translators/workgraph/`)

Two files:

- **`agency-assign-workgraph`** — bash script run once before `wg service start`. Reads all open tasks, sends to `POST /projects/{id}/assign`, stores returned prompts and task IDs.
- **`agency-wg-executor.sh`** — called by Workgraph for each task. Reads the pre-stored prompt, runs Claude, marks complete, fetches evaluator, posts result.

**Setup:**

```bash
agency token create --client-id workgraph > ~/.agency-workgraph-token
export AGENCY_PROJECT_ID="<your-project-id>"
export AGENCY_TOKEN_FILE="$HOME/.agency-workgraph-token"
```

### Superpowers (`translators/superpowers/agency-dispatch/`)

A skill file (`SKILL.md`) that replaces `dispatching-parallel-agents` when Agency is configured. Checks Agency reachability, falls back to standard dispatch if unreachable, extracts tasks from the current plan, calls batch assignment, dispatches subagents with rendered prompts, and posts evaluator results.

```bash
agency token create --client-id superpowers > ~/.agency-superpowers-token
```

---

## Error handling

Agency emails the resolved contact address when it encounters a problem it cannot resolve. Contact email, oversight preference, and error notification timeout are resolved using the instance/project hierarchy.

| Error type | Behaviour |
|---|---|
| Primitive store empty | 503 response; email notification to contact |
| LLM call failure | Retry until timeout; email contact; resume when reachable |
| No agent can be created for task | Email contact immediately |
| Task clarification timeout | Email contact after timeout; task remains pending |
| SMTP failure | Logged only — cannot email about email failure |

### SMTP configuration

Uses Python's standard library `smtplib` with TLS. Configured in `agency.toml [smtp]`. If `[smtp]` is absent or incomplete, Agency logs the error and the notification intent but does not attempt to send email.

---

## Tech stack

| Component | Choice |
|---|---|
| Language | Python 3.13 |
| API framework | FastAPI |
| Storage | SQLite |
| Vector storage | sqlite-vec |
| Embedding model | `sentence-transformers all-MiniLM-L6-v2` (local, CPU-only) |
| JWT library | `pyjwt` with `cryptography` backend (EdDSA signing) |
| MCP | `mcp>=1.26.0` (Anthropic MCP Python SDK) |
| Deployment | pip install (`agency-engine`) |

### Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | HTTP API |
| `uvicorn` | ASGI server |
| `pyjwt` | JWT creation and verification |
| `cryptography>=42.0` | Ed25519 keypair generation, EdDSA support for pyjwt |
| `mcp>=1.26.0` | MCP server implementation |
| `sentence-transformers` | Local embedding model |
| `sqlite-vec` | Vector similarity search |
| `tomli` / `tomli-w` | TOML config read/write |
| `httpx` | HTTP client for auto-start health checks and MCP-to-API calls |

---

## Required setup sequence

```bash
# Step 1 — Install (pipx recommended — keeps agency on PATH across sessions)
pipx install agency-engine

# Step 2 — Full setup wizard
agency init

# Step 3 — Start server
agency serve
```

All configuration, database initialisation, primitive installation, project creation, and token creation are handled by `agency init`. When using Agency via MCP in Claude Code, the server is started automatically (see Zero-terminal).

---

## Compatibility with v1.1.0

All v1.1.0 functionality is preserved. v1.2.0 is additive with these exceptions:

1. **JWT algorithm changes from `HS256` to `EdDSA`.** All v1.1.0 tokens are invalid after upgrading. Recreate with `agency token create`.

2. **`agency.toml` restructured.** `[auth] jwt_secret` removed. New sections: `[llm]`, `[notifications]`, `[smtp]`, `[output]`.

3. **`agency token create` generates a `jti` claim** and writes to `issued_tokens`. Requires the database to exist.

4. **`projects` table gains new columns:** `name`, `contact_email`, `oversight_preference`, `error_notification_timeout`, `llm_provider`, `llm_model`, `llm_api_key`, `homepool_retry_max_interval`, `permission_block`, `attribution`. Existing rows receive defaults via migration.

5. **`primitives` table gains new columns:** `quality`, `domain_specificity`, `domain`, `origin_instance_id`, `parent_content_hash`, `permission_block`, `override_capability`. Existing primitives receive defaults via migration.

6. **`compositions` table gains `permission_block`.** Existing compositions receive the default.

7. **New tables:** `issued_tokens`, `pending_evaluations`, `primitive_mutations`.

8. **`POST /tasks/{id}/evaluation` response** now returns `{"status": "ok", "content_hash": "<sha256>"}` (changed from `"accepted"` in v1.2.2).

### Compatibility with v1.2.1

v1.2.2 is additive with these exceptions:

1. **Submit response `status` changes from `"accepted"` to `"ok"`.** Requesters parsing `status == "accepted"` must update.
2. **All error responses gain `error_type` field.** Additive — existing parsers that ignore unknown fields are unaffected.
3. **Assign response gains `task_ids` summary block.** Additive.
4. **`agents` table gains `template_id` column** via migration. Existing rows auto-populate with `"default"`. Inert in v1.2.2.
5. **`agent_hash` in status endpoint** now returns `agents.content_hash` (SHA-256) instead of `agent_composition_id` (UUID).

### Compatibility with v1.2.2

v1.2.3 is additive with these exceptions:

1. **`scope` column added to all three primitive tables** (`role_components`, `desired_outcomes`, `trade_off_configs`) via migration. `TEXT NOT NULL DEFAULT 'task'`. Existing rows default to `'task'`. The `primitives` view is dropped and recreated to include `scope`.

2. **`agency.toml` gains `[assigner]` section.** Additive — absent section defaults to `strategy = "embedding"`.

3. **`composition-rules.csv` created on first serve.** New file at `~/.agency/composition-rules.csv` with 5 starter rules. User-editable; `agency primitives update` does not overwrite it.

4. **Assign response gains `composition_fitness` per agent.** Additive.

5. **New endpoint: `POST /triage`.** Additive.

6. **New MCP tool: `agency_triage`.** Additive — tool count increases from 7 to 8.

7. **`first_run_onboarding` field injected on first successful MCP call.** One-time, additive. Controlled by `~/.agency/.onboarded` marker file.

8. **Starter CSV gains `scope` column.** Existing CSV parsers that ignore unknown columns are unaffected. Run `agency primitives update` after upgrade to ingest 7 new metaprimitives.

9. **New bundled skills:** `agency-getting-started`, `agency-composition-config`. Run `agency skills install` to install.
