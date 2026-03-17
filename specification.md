# Agency — specification v1.2.1
*2026-03-17*

---

## Purpose and scope

Agency is a standalone service for composing, assigning, evaluating, and evolving AI agents. It is released under Elastic License 2.0. This licence permits self-hosting for internal use without restriction. The one thing it does not permit is offering Agency as a managed or hosted service commercially. If you are running Agency for your own organisation's tasks, the licence does not affect you.

Agency does not execute tasks. It composes and assigns agent descriptions; the task manager executes tasks using those descriptions. Agency works with any task management system.

v1.2.0 adds native MCP integration for Claude Code, Ed25519 authentication, token management, the permission model, a two-phase setup wizard, instance/project configuration hierarchy, agent output attribution, primitive quality scores and distribution, and SMTP error notification.

---

## Core concepts

### Primitives

Agency stores three types of primitives independently:

- **Role components** — individual capabilities: the ability to do a specific thing
- **Desired outcomes** — what success looks like for a type of work
- **Trade-off configurations** — acceptable and unacceptable trade-offs governing how work is done

These are stored as independent, uncommitted objects. Pre-composed agents are a cache on top of this primitive store, not the ground truth.

Each primitive carries a quality score (integer, 0-100). The assigner only selects primitives with quality > 90 for new compositions. Quality scores are set at primitive creation time and updated by `agency primitives update` from the upstream starter CSV.

### Agents and actor-agents

An **agent** is a composition of role components + desired outcomes + trade-off configuration. It is a deployable configuration that may exist in the composition cache without being assigned to any task.

An **actor-agent** is an agent that has been assigned to a specific task and is actively performing it.

### Self-similar system

All special-type agents — assigner, evaluator, evolver, agent creator — are first-class agents governed by the same primitive structure as every other agent. None are privileged system components. All accumulate performance history and are subject to selection pressure.

### Batch assignment

A single API call that accepts a complete set of task descriptions, composes an agent for each, deduplicates similar compositions, and returns a packet containing all assignments and all unique agent definitions. The calling tool stores this packet locally and does not need to call Agency again during execution.

This is the preferred integration pattern for task management tools. It replaces per-task calls during execution with a single pre-flight call before execution begins.

### MCP integration

Agency registers as a local MCP server in Claude Code. When registered, Claude Code calls Agency tools natively during planning and dispatch — without the user invoking a skill or writing shell commands. The MCP server translates tool calls into authenticated HTTP calls to the running `agency serve` process.

### Instance/project configuration hierarchy

Seven settings operate on a two-level hierarchy. The instance level (in `agency.toml`) sets the default for the entire installation. Individual projects can override any of these settings independently. A project that does not override a setting inherits the current instance value dynamically.

The seven hierarchical settings are: contact email, oversight preference, error notification timeout, attribution, LLM provider, LLM model, and LLM API key.

Resolution rule: the project column value is used if non-null; otherwise the instance value is used. A null project value means "use whatever the instance is currently set to." If the instance setting is later changed, all projects with null for that field inherit the new value automatically.

---

## Data model

### Primitive store

Each primitive record stores:

| Field | Notes |
|---|---|
| `id` | UUID v7 (globally unique, time-ordered) |
| `description` | Natural language string |
| `content_hash` | SHA-256 of description — stable identity, deduplication |
| `embedding` | Semantic vector — used for similarity search and evolution |
| `quality` | Integer 0-100 — selection eligibility threshold (> 90 required) |
| `domain_specificity` | Integer 0-100 — how domain-specific this primitive is |
| `domain` | JSON array of strings (e.g. `["research","writing"]`) — empty array means domain-neutral |
| `origin_instance_id` | UUID of the instance that created this primitive; `00000000-0000-7000-8000-000000000001` for official starter primitives |
| `parent_content_hash` | Content hash of the primitive this was evolved from; null for originals |
| `permission_block` | 26-character encoded string (see Permission model) |
| `override_capability` | 12-character encoded string or null (role components only) |
| `instance_id`, `client_id`, `project_id` | UUID v7s (provenance) |
| Performance metadata | Former agents it was part of; evaluations received |

### Composition cache

Pre-composed agents on top of the primitive store. Each agent record stores the IDs of its constituent primitives, a content hash of the composition, its permission block (26-character encoded string), and its performance history. The cache is a performance optimisation; the primitive store is the ground truth.

### Projects

Each project record stores:

| Field | Notes |
|---|---|
| `id` | UUID v7 |
| `name` | String |
| `client_id` | Optional UUID v7 |
| `description` | Optional string |
| `contact_email` | Nullable — null inherits instance default |
| `oversight_preference` | `discretion` or `review` — nullable, null inherits |
| `error_notification_timeout` | Integer seconds — nullable, null inherits |
| `attribution` | Integer (1=on, 0=off) — nullable, null inherits |
| `llm_provider` | Nullable — null inherits instance LLM backend |
| `llm_model` | Nullable — null inherits instance model |
| `llm_api_key` | Nullable — null inherits instance API key |
| `homepool_retry_max_interval` | Integer seconds — nullable, system default 3600; no effect in v1.2.0 |
| `permission_block` | 13-character encoded string — default `1400000000006` |
| `created_at` | ISO timestamp |

### Tasks

Each task record stores:

| Field | Notes |
|---|---|
| `id` | UUID v7 (Agency's internal ID) |
| `external_id` | The calling tool's own identifier — optional, stored for the caller's use |
| `project_id` | Optional UUID v7 |
| `description` | Task description |
| `output_format`, `output_structure`, `clarification_behaviour` | Task parameters |
| `agent_composition_id` | Set after assignment — FK to composition cache |
| `created_at` | ISO timestamp |

Tasks persist across server restarts.

### Issued tokens

| Field | Notes |
|---|---|
| `jti` | UUID v7 — primary key, included as JWT claim |
| `client_id` | String — identifies the integration (e.g. `mcp`, `superpowers`, `workgraph`) |
| `created_at` | ISO timestamp |
| `expires_at` | Optional ISO timestamp |
| `revoked` | Integer (0 or 1) |
| `revoked_at` | Optional ISO timestamp |

### Pending evaluations

| Field | Notes |
|---|---|
| `id` | UUID v7 |
| `task_id` | UUID v7 |
| `evaluator_data` | JSON — evaluator description + evaluation payload |
| `content_hash` | SHA-256 of evaluator_data |
| `destination` | `agency_instance` or `home_pool` |
| `created_at` | ISO timestamp |
| `last_ping_at` | Optional ISO timestamp |
| `confirmed_at` | Optional ISO timestamp |
| `confirmed` | Integer (0 or 1) |

Populated on every evaluation submission. The `agency_instance` row is confirmed immediately after processing. The `home_pool` destination is not active in v1.2.0.

### Primitive mutations

| Field | Notes |
|---|---|
| `id` | UUID v7 |
| `content_hash` | Identifies the primitive (stable across metadata changes) |
| `field` | `quality`, `domain_specificity`, or `domain` |
| `old_value` | Previous value; null if first recorded |
| `new_value` | New value |
| `changed_by` | Instance ID that made the change |
| `changed_at` | ISO timestamp |
| `evidence` | JSON — e.g. `{"source": "upstream_csv", "fetched_at": "<timestamp>"}` |

Written by `agency primitives update` whenever it changes quality, domain_specificity, or domain from the upstream CSV.

### Unique identifiers

All IDs are UUID v7: globally unique without coordination, time-ordered. The instance ID is generated during `agency init` Phase 1.

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

## Permission model

Every primitive and every composed agent carries a permission block encoding who may access or modify it, whether that authorisation is permanent or time-limited, and whether it can be re-delegated.

### 13-character block encoding

| Position | Values | Meaning |
|---|---|---|
| 1 | `0` `1` `2` `3` | Access: `0`=default, `1`=human only, `2`=machine only, `3`=human or machine |
| 2 | `4` `5` | Duration: `4`=permanent, `5`=time-limited |
| 3-12 | 10-digit Unix timestamp | Expiry — zeros if permanent |
| 13 | `6` `7` `8` `9` | Re-delegation: `6`=none, `7`=human only, `8`=machine only, `9`=human or machine |

Default: `1400000000006` (human-only, permanent, no re-delegation).

### 26-character permission block

Agents and primitives carry two concatenated 13-character blocks:

- **Block 1 (positions 1-13):** inherited from project
- **Block 2 (positions 14-26):** entity-level override

Resolution: if Block 2 is non-default (position 14 is not `0`), Block 2 governs. Otherwise Block 1 governs.

Projects carry a single 13-character block, copied into Block 1 of every entity created within the project.

### Override capability on role components

A role component may carry an `override_capability` — a 12-character string granting access within a defined scope, bypassing the permission block check.

| Position | Values | Meaning |
|---|---|---|
| 1 | `1` `2` `3` `4` | Scope: `1`=project, `2`=agent, `3`=primitive, `4`=all |
| 2 | `4` `5` | Duration: `4`=permanent, `5`=time-limited |
| 3-12 | 10-digit Unix timestamp | Expiry — zeros if permanent |

### Default permissions

All primitive types default to human-only, permanent, no re-delegation (`1400000000006`). The evolver and agent creator cannot modify or create primitives without explicit human delegation.

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

Transport: stdio. Launched by Claude Code as a subprocess. Requires `agency serve` to be running.

At startup, reads: Agency URL from `agency.toml`, JWT token from `AGENCY_TOKEN_FILE` (default: `~/.agency-mcp-token`), default project ID from `AGENCY_PROJECT_ID` env var or `agency.toml [project] default_id`.

Three tools:

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

Calls `POST /tasks/{agency_task_id}/evaluation`. Returns `{"status": "accepted", "content_hash": "<sha256>"}`. The caller should verify the returned content hash against the SHA-256 of the payload sent.

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

The batch endpoint is the preferred integration pattern. The calling tool sends all tasks at once before execution begins. Agency returns a packet mapping each task to a composed agent and including all unique agent definitions. Tasks that compose to similar agents (cosine similarity >= 0.90) share a single agent definition.

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

The `agents` map is deduplicated. The response now includes `permission_block` per agent composition. If the primitive store is empty, the endpoint returns `503` with `{"error": "primitive_store_empty"}`.

### Callbacks from field (evaluator -> Agency)

| Direction | Signal |
|---|---|
| IN | Full evaluation report — `POST /tasks/{id}/evaluation` |

The endpoint computes SHA-256 of the received payload and returns `{"status": "accepted", "content_hash": "<sha256>"}`. The caller verifies the returned hash against the hash of what was sent. Duplicate submissions (same `jti` + `task_id`) are rejected with `{"status": "duplicate"}`.

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

## Internal agent types

### Assigner

The assigner matches incoming tasks to agent configurations from the composition cache, or composes new configurations from primitives when no suitable cached agent exists. It weighs matches by historical performance and filters to primitives with quality > 90. When a task is underspecified, the assigner can request clarification before assigning.

### Evaluator

The evaluator grades completed actor-agent tasks. It is not run inside Agency. It is rendered as a markdown agent description and sent to the task manager alongside the task agent. It runs in the task manager's environment. On task completion it calls back directly to the client's Agency instance.

The callback JWT is baked into the evaluator's markdown at creation time, bound to a specific task. Reports where the task ID in the body does not match the JWT are rejected. Each JWT can be consumed only once.

### Evolver

The evolver modifies primitives and their configurations. Its mutation strategies are themselves first-class role components stored in the primitive store. The evolver targets two dimensions: (1) level — individual primitive, composition, or agent; (2) amount — minimal, moderate, or maximal change.

Evolution of trade-off configurations may proceed automatically. Evolution of desired outcomes requires human sign-off.

### Agent creator

The agent creator expands the primitive store by searching outside the agency for new role components, desired outcomes, and trade-off configurations.

### Renderer

The renderer takes role components + desired outcomes + trade-off configurations + task description and produces a single short markdown document. When attribution is enabled, the renderer appends the attribution instruction in the appropriate format. The rendering template is an evolvable parameter.

---

## Primitive distribution

The starter primitive set is hosted as a CSV file in the public Agency GitHub repository and fetched at init time. It is not bundled in the pip package.

**CSV columns:** `type`, `name`, `description`, `quality`, `domain_specificity`, `domain`, `origin_instance_id`, `parent_content_hash`.

### `agency primitives update`

```bash
agency primitives update
```

Fetches the current starter CSV and reconciles with the local store:

1. **New primitives** (content hash not in local store, quality > 90): inserted with all CSV fields
2. **Existing primitives with changed quality, domain_specificity, or domain**: local columns updated; one row written to `primitive_mutations` per changed field
3. **Unchanged primitives**: no action
4. **Local primitives not in upstream CSV**: no action (may be locally created)
5. **`parent_content_hash`**: stored on ingest for new primitives; immutable once set

Quality threshold is hardcoded at > 90 in v1.2.0.

---

## Setup and CLI

### `agency init` — two-phase setup wizard

Covers the full installation lifecycle. Every step checks whether it has already been completed and skips if so. Safe to re-run at any time.

**Phase 1 — Configuration (6 steps, no server required):**

| Step | What | Input |
|---|---|---|
| 1.1 | Generate instance credentials (UUID v7, Ed25519 keypair) | Automatic |
| 1.2 | Configure server settings (host, port) | Automatic |
| 1.3 | Configure LLM connection | User selects backend and provides credentials |
| 1.4 | Configure notifications (contact email, timeout, oversight, SMTP) | User input |
| 1.5 | Configure output defaults (attribution) | Automatic |
| 1.6 | Register with Claude Code (MCP server in `~/.claude.json`) | User confirms |

**Phase 2 — Initialisation (6 steps, runs the server briefly):**

| Step | What | Input |
|---|---|---|
| 2.1 | Initialise database (start server, run migrations, stop) | Automatic |
| 2.2 | Download embedding model (`all-MiniLM-L6-v2`, ~80MB) | Automatic |
| 2.3 | Install starter primitives (fetch CSV from GitHub) | User confirms |
| 2.4 | Create first project (runs project creation wizard) | User input |
| 2.5 | Create integration tokens (MCP, Superpowers, Workgraph) | User selects |
| 2.6 | Install Claude Code skill (`agency-primitive-extraction`) | Automatic |

### `agency client setup`

```bash
agency client setup
```

Reviews and updates instance-level settings. Shows the current value of every setting; press enter to keep or type a new value to change. Includes protective behaviours for high-impact changes: keypair rotation requires typed confirmation and revokes all tokens; LLM changes run a connection test; contact email changes note which projects inherit.

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

Bundled skills in v1.2.0:
- `agency-primitive-extraction` — guides Claude through extracting and authoring Agency primitives from existing prompts and agent descriptions

### Token commands

```bash
agency token create --client-id <name>    # create, print to stdout
agency token list                          # table of all issued tokens
agency token revoke --client-id <name>     # revoke all tokens for a client
```

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

### Content hash confirmation

When `POST /tasks/{id}/evaluation` receives a payload, it computes SHA-256 of the received body, writes a row to `pending_evaluations`, processes the evaluation, marks the row confirmed, and returns the content hash. The caller verifies the returned hash against what was sent.

---

## Evolution mechanism

Primitives carry both a content hash (identity) and a semantic embedding (position in meaning-space). The evolver operates on these differently: content hashes track versions; embeddings are mutation targets.

Parallel evaluations: N variant agents, identical except for one mutated primitive, run against the same task. The best-performing variant is selected. This is token-intensive and triggered explicitly.

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

All configuration, database initialisation, primitive installation, project creation, and token creation are handled by `agency init`.

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

8. **`POST /tasks/{id}/evaluation` response** now returns `{"status": "accepted", "content_hash": "<sha256>"}`.
