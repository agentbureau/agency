# Agency — specification v1.2.4.1
*2026-03-30*

## Setting up Agency for the first time

Tell Claude Code:

> "Install and set up Agency from github.com/agentbureau/agency"

Claude will run the install, setup wizard, and MCP registration. Once complete, Agency tools (`agency_assign`, `agency_evaluator`, `agency_submit_evaluation`, etc.) are available natively in Claude Code.

For manual installation:

```bash
pipx install --python python3.13 agency-engine
agency init
```

The `/agency-getting-started` skill provides an interactive walkthrough of the full workflow: composing agents, executing tasks, and submitting evaluations.

---

## Purpose and scope

Agency is a standalone service for composing, assigning, evaluating, and evolving AI agents. It is released under Elastic License 2.0. This licence permits self-hosting for internal use without restriction. The one thing it does not permit is offering Agency as a managed or hosted service commercially. If you are running Agency for your own organisation's tasks, the licence does not affect you.

Agency does not execute tasks. It composes and assigns agent descriptions; the task manager executes tasks using those descriptions. Agency works with any task management system, and Claude Code (which manages tasks too).

v1.2.4 adds task-type pre-classification (12-type keyword classifier), a composition fitness floor at 0.39 (advisory, not gate), a three-signal triage advisory (task type + fitness + method absence), evaluation cascade from compositions to individual primitives, experiment tracking (assignment candidate persistence), multi-dimensional evaluation storage, primitive lineage tracking (parent_ids, generation, created_by), explore/exploit assignment counting, a CLI primitive import command, an `agency_update_primitives` MCP tool, and status file operationalisation (version notifications, announcement tracking, primitives update advisory).

---

## Core concepts

### Primitives

Agency stores three types of primitives independently:

- **Role components** — individual capabilities: the ability to do a specific thing
- **Desired outcomes** — what success looks like for a type of work
- **Trade-off configurations** — acceptable and unacceptable trade-offs governing how work is done

These are stored as independent, uncommitted objects. Pre-composed agents are a cache on top of this primitive store, not the ground truth.

Each primitive carries a quality score (integer, 0-100). The assigner only selects primitives with quality > 90 for new compositions. Quality scores are set at primitive creation time and updated by `agency primitives update` from the upstream starter CSV. Quality scores are currently defaulted to 100; when evolution tools are launched (probably in v1.3.0), primitive quality scores will begin to change based on the performance of agents built with those primitives.

#### Lineage (v1.2.4)

Each primitive tracks its derivation history:

- `parent_ids` — JSON list of parent primitive content hashes (NULL for originals). Supports multi-parent crossover evolution.
- `generation` — integer, default 0. Incremented on each mutation.
- `created_by` — provenance: `"human"` (default), `"import"`, `"evolver"`, `"agent_creator"`.
- `reframing_potential` — nullable float. Forward-compatible infrastructure for distinguishing reframing primitives (which introduce qualitatively different analytical lenses) from execution-describing primitives. Not populated in v1.2.4.

The existing `parent_content_hash` column is frozen — retained for backward compatibility but new code reads and writes `parent_ids` only.

### Metaprimitives

A metaprimitive is a primitive that governs how Agency itself operates — as distinct from task primitives composed into requester-facing agents. Metaprimitives live in the same primitive tables as task primitives, distinguished by a `scope` column. Values: `task` (default), `meta:assigner`, `meta:evaluator`, `meta:evolver`, `meta:agent_creator`.

v1.2.3 ships 7 starter assigner metaprimitives.

### Composition config

`~/.agency/composition-rules.csv` governs how Agency's functional agents are composed. It is a watched file: changes take effect on the next composition call without server restart. Editable directly or via the `agency-composition-config` skill in Claude Code.

### Task-type classification (v1.2.4)

Before embedding search, `classify_task_type(description)` categorises the task into one of twelve types: `research`, `build`, `review`, `analyse`, `write`, `design`, `debug`, `plan`, `audit`, `evaluate`, `advise`, `synthesise`. Falls back to `analyse` if no keywords match. The classification is used by the triage endpoint's three-signal model and is included in `composition_fitness` responses.

Implementation: keyword heuristic (no LLM call). The classifier runs before `find_similar()` in the composition pipeline.

### Composition fitness (v1.2.4)

Every `agency_assign` response includes `composition_fitness` with:

- `mean_fitness` — mean cosine similarity across all selected primitives
- `pool_match` — advisory band: `"low"` (< 0.39), `"moderate"` (0.39–0.50), `"good"` (> 0.50)
- `task_type` — classified task type from the pre-classifier
- `capability_caveat` — present when `task_type` is `"research"`: warns that composition primitives frame analytical method but cannot supply domain knowledge

The fitness floor (0.39) is advisory, not a gate — compositions proceed regardless. The value is adjustable via `agency.toml` (`[assigner] composition_fitness_floor`) or the status file without a code release.

### Triage

A lightweight, stateless, read-only check (`POST /triage`) that returns the best-matching primitives for a task description without performing full composition. v1.2.4 extends triage with a three-signal compose recommendation:

- **Signal 1: Task type** — from `classify_task_type()`. Mapped to Agency probability: high (review/audit/advise), moderate (analyse/evaluate/synthesise), neutral (design/build/plan/debug), low (write/research).
- **Signal 2: Fitness estimate** — mean similarity of top matches. Banded as low/moderate/good.
- **Signal 3: Method absence** — heuristic estimate of whether the prompt already prescribes the analytical method. Higher = more room for Agency to add value.

Recommendation values: `"compose"` (favourable), `"compose_with_advisory"` (mixed signals), `"compose_unlikely_to_help"` (unfavourable, with `reason` field).

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

[assigner]
strategy = "embedding"           # or "llm"
composition_fitness_floor = 0.39 # optional override (v1.2.4)

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

[status]
url = "https://raw.githubusercontent.com/agentbureau/agency/main/agency-status.json"
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

### Evaluator tokens

Single-use callback tokens issued by `GET /tasks/{id}/evaluator`. Scope: `evaluator:<task_id>`. Include evaluator agent metadata in claims.

v1.2.4: `submit_evaluation()` accepts callback JWT in the request body (primary) or Authorization header (fallback with deprecation warning). Body-provided `evaluator_agent_id` takes precedence over JWT claims.

### Token management

- `agency token create --client-id <name>` — issue a new token
- `agency token revoke <jti>` — revoke by JTI
- `agency token list` — list all issued tokens

---

## Agent output attribution

When `attribution = true` (default), every rendered agent prompt includes a footer line attributable to Agency: the agent's unique ID and composition hash. This survives output forwarding. Attribution can be disabled per-instance in `agency.toml [output]` or per-project.

---

## Integration surface

### MCP server (`agency mcp`)

Transport: stdio. Tools (v1.2.4):

| Tool | Purpose |
|---|---|
| `agency_assign` | Compose agents for a batch of tasks |
| `agency_evaluator` | Get evaluator prompt + callback JWT for a task |
| `agency_submit_evaluation` | Submit evaluation with callback JWT |
| `agency_get_task` | Retrieve task state, agent, evaluation |
| `agency_list_projects` | List all projects |
| `agency_create_project` | Create a new project |
| `agency_status` | Instance status, task progress, primitive health |
| `agency_update_primitives` | Update primitive pool from upstream starter CSV |

`agency_update_primitives` (v1.2.4) bypasses the API server — it calls `reconcile_from_csv()` directly against the shared SQLite database. All other tools route through the HTTP API via `client.py`.

#### `agency_assign`

```json
{
  "tasks": [
    {
      "external_id": "my-task-1",
      "description": "Review the API design for consistency issues",
      "skills": ["api-design"],
      "deliverables": ["review-report.md"]
    }
  ],
  "project_id": "optional-uuid"
}
```

Response includes `assignments` (mapping external_id to agency_task_id and agent_hash), `agents` (mapping agent_hash to rendered_prompt, primitive_ids, composition_fitness), and `task_ids` summary.

`composition_fitness` (v1.2.4) includes:
- `per_primitive_similarity` — per-primitive cosine similarity scores
- `mean_fitness` — mean across all selected primitives
- `pool_match` — `"low"` / `"moderate"` / `"good"`
- `task_type` — classified task type
- `capability_caveat` — present for research tasks

#### `agency_evaluator`

Response includes `rendered_prompt`, `evaluator_prompt` (deprecated alias — use `rendered_prompt`; alias removal in v1.3.0), `callback_jwt`, `evaluator_agent_id`, `content_hash`, `template_id`.

#### `agency_submit_evaluation`

Accepts: `agency_task_id`, `callback_jwt`, `output`, and optional `score`, `task_completed`, `score_type`, `dimensional_scores`.

`dimensional_scores` (v1.2.4) is an optional JSON object with caller-defined dimensions, e.g., `{"correctness": 85, "completeness": 70}`. Stored alongside the scalar score. v1.2.4: storage only — no downstream consumption.

After storing the evaluation, a cascade propagates the score to all primitives in the composition (equal propagation — same score to each role component, desired outcome, and trade-off config).

#### `agency_status`

Response includes project list, task summaries, primitive counts. v1.2.4 additions:
- `version_update_available` — present when a newer Agency version exists
- `announcements` — unseen entries from the status file (displayed once per instance)
- `primitives_update_available` — advisory when the status file signals a starter pack update

#### `agency_update_primitives` (v1.2.4)

No parameters required. Fetches the latest starter CSV from GitHub, reconciles with the local store. Returns counts: `new`, `updated_primitives`, `fields_changed`, `unchanged`, `below_threshold`, `failed`.

### Triage endpoint (v1.2.4)

`POST /triage` — lightweight pre-composition check.

Request body:
```json
{"description": "Review the API design for consistency issues"}
```

Response (v1.2.4):
```json
{
  "matched_primitives": [{"name": "...", "type": "role_component", "similarity": 0.45}],
  "task_type": "review",
  "fitness_estimate": 0.43,
  "method_absence_estimate": 0.7,
  "recommendation": "compose",
  "reasoning": "Task type: review (high Agency probability). Fitness estimate: 0.430 (moderate). ...",
  "signals": {
    "task_type": "review",
    "task_type_agency_probability": "high",
    "fitness_estimate": 0.43,
    "fitness_band": "moderate",
    "method_absence_estimate": 0.7,
    "method_absence_band": "high"
  },
  "warning": null
}
```

Recommendation values: `"compose"`, `"compose_with_advisory"`, `"compose_unlikely_to_help"`. The `reason` field is present only when recommendation is `"compose_unlikely_to_help"`.

### CLI task commands (v1.2.2)

```bash
agency task assign    --description "..." [--project-id UUID]
agency task evaluator --task-id UUID
agency task submit    --task-id UUID --callback-jwt TOKEN --output "..."
agency task get       --task-id UUID
```

### CLI primitive commands

```bash
agency primitives install    # Fetch and install starter set from GitHub
agency primitives update     # Reconcile with latest upstream CSV
agency primitives list       # List stored primitives
agency primitives import <path> [--instance-id ID] [--dry-run]  # v1.2.4
```

`agency primitives import` (v1.2.4) reads a local CSV, validates against the starter schema (required: `type`, `name`, `description`), deduplicates by content hash, and inserts with `created_by = "import"`. Supports `--dry-run` for validation without writes.

### Error response schema (v1.2.2)

All error responses include:

```json
{
  "status": "error",
  "error_type": "validation | authentication | permanent | transient",
  "code": 422,
  "message": "Human-readable error description",
  "cause": "What went wrong",
  "fix": "What to do about it"
}
```

### Project level

```
POST /projects         — create project
GET  /projects         — list projects
GET  /status           — instance status (compact without project_id, detailed with)
```

### Task level — individual

```
POST /tasks            — create task
GET  /tasks/{id}       — get task state (assigned / evaluation_pending / evaluation_received)
GET  /tasks/{id}/agent — compose and assign agent
GET  /tasks/{id}/evaluator — get evaluator prompt + callback JWT
POST /tasks/{id}/evaluation — submit evaluation
```

### Task level — batch

```
POST /projects/{id}/assign — batch assign (preferred path)
```

### Callbacks from field (evaluator -> Agency)

The evaluator callback uses a single-use JWT. v1.2.4: body is the primary path; Authorization header is a fallback (with deprecation warning).

### Evolution oversight

Oversight preferences: `review` (require human confirmation), `discretion` (agency decides), `full_autonomy`. Set at instance or project level.

### Admin

```
POST /tokens           — issue token
DELETE /tokens/{jti}    — revoke token
GET  /tokens            — list tokens
```

---

## Primitive distribution

The starter primitive set is hosted as a CSV in the public Agency GitHub repository and fetched at init time. This keeps the pip package small and allows the primitive set to be updated independently of software releases.

### `agency primitives update`

Fetches the current CSV and reconciles with the local store: inserting new primitives above the quality threshold, updating quality scores and metadata on existing ones, and leaving locally-evolved primitives untouched.

v1.2.4: per-row commits — a single row failure does not abort the remaining rows. Failed rows are reported with actionable error messages.

---

## Data foundation (v1.2.4)

### Primitive performance

The `primitive_performance` table stores running aggregates per primitive:
- `evaluation_count`, `avg_score` — from evaluation cascade
- `assignment_count`, `last_assigned_at` — from assignment tracking

**Evaluation cascade:** after `submit_evaluation()` stores a composition-level score, it propagates to all constituent primitives. v1.2.4: equal propagation (same score to all). More sophisticated attribution deferred to v1.3.0.

**Assignment tracking:** `assignment_count` increments on every `assign_agent()` call. Provides the exploitation signal a future UCB1 explorer needs.

### Assignment candidates

The `assignment_candidates` table stores all candidates considered during each assignment, with similarity scores and selection flags. Enables retrospective analysis of selection strategies and pool health diagnostics.

### Dimensional evaluation

The `dimensional_scores` column on `pending_evaluations` stores optional caller-defined dimensional breakdowns alongside the scalar score. v1.2.4: storage only — no downstream consumption. The schema is intentionally unstructured (JSON object) to avoid locking in a taxonomy prematurely.

---

## Status file (v1.2.4)

`agency-status.json` in the public GitHub repo acts as a zero-infrastructure control plane. Instances poll it on first MCP tool call per session (not periodic background).

**Acting on fetched data:**
- Version notifications in `agency_status` responses
- Unseen announcements displayed once per instance (tracked in `seen_announcement_ids`)
- Primitives update advisory — resurfaces each session until the user runs the update

The composition fitness floor is adjustable via the status file without a code release.

---

## Setup and CLI

### `agency init` — two-phase setup wizard

Phase 1 (6 steps, no server required): configuration.
Phase 2 (5 steps, runs the server briefly): database, primitives, project, token.

Every step is idempotent — the wizard can be re-run at any time and skips completed steps.

v1.2.4: three-layer terminal typography (status/helper/prompt) with TTY detection.

### `agency serve`

Starts the API server. v1.2.4: clean shutdown on Ctrl+C (no asyncio/uvicorn traceback).

### `agency client setup`

Interactive guided setup for a client machine connecting to a remote Agency instance. Writes `agency.toml` with remote host/port/token.

### `agency project create`

Interactive project creation. Settings not specified inherit from instance defaults.

### `agency skills install`

Installs Agency skills into `~/.claude/skills/`. Skills: `agency-getting-started`, `agency-composition-config`, `agency-primitive-extraction`.

### Token commands

```bash
agency token create --client-id <name>
agency token revoke <jti>
agency token list
```

---

## Zero-terminal

### MCP auto-start

When Claude Code invokes an Agency MCP tool, the MCP server checks if `agency serve` is running (health check). If not, it spawns the server automatically. The user does not need a terminal tab running `agency serve`.

### Non-interactive flags

`agency init --non-interactive` completes setup using defaults without prompts. Essential for CI/CD and environments where `stdin` is not available.

---

## Translators

### MCP (Claude Code)

The native integration path. `agency mcp` registers as an MCP server in `~/.claude.json`.

### Workgraph (`translators/workgraph/`)

`agency-wg-executor.sh` bridges Agency with Workgraph's task execution model.

v1.2.4 fixes: `evaluator_prompt` → `rendered_prompt` field rename (Issue 9), callback JWT moved from header to body (Issue 10), `evaluator_agent_id` forwarding (Issue 11).

### Superpowers (`translators/superpowers/agency-dispatch/`)

Legacy integration path. Available as a fallback for environments without MCP support.

---

## Error handling

Agency uses structured error classification (`error_type`) to help callers handle errors programmatically. `validation` errors indicate bad input and should not be retried. `transient` errors (network, timeout) should be retried with backoff. `permanent` errors indicate configuration or state problems requiring human intervention.

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
| `packaging>=21.0` | Semantic version comparison for status file notifications (v1.2.4) |

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

## Schema migrations (v1.2.4)

| Migration | Function | What it does |
|---|---|---|
| 6 | `add_lineage_columns` | Adds `parent_ids`, `generation`, `created_by`, `reframing_potential` to all primitive tables; recreates `primitives` view; adds name column indexes |
| 7 | `add_assignment_candidates` | Creates `assignment_candidates` table with task and primitive indexes |
| 8 | `add_primitive_performance` | Creates `primitive_performance` table and `cascaded_evaluation_ids` table |
| 9 | `add_dimensional_scores` | Adds `dimensional_scores` column to `pending_evaluations` |

All migrations are additive (new columns or new tables). All ALTER TABLE statements use idempotency guards (try/except for duplicate column name) to handle the MCP/API migration race condition.

---

## Compatibility with v1.2.3

v1.2.4 is additive with these exceptions:

1. **`TaskRequest.output_format` default changes from `"json"` to `"markdown"`.** Callers depending on JSON output must explicitly pass `output_format: "json"`.

2. **Triage `recommendation` field changes from two values to three.** `"skip-safe"` is retired. New values: `"compose"`, `"compose_with_advisory"`, `"compose_unlikely_to_help"`. Callers checking `recommendation == "skip-safe"` must update.

3. **Triage response gains new fields:** `task_type`, `fitness_estimate`, `method_absence_estimate`, `signals`, and optional `reason`. Additive — existing parsers that ignore unknown fields are unaffected.

4. **`_assign_via_embedding()` return type changes from tuple to dict.** Internal function — no external callers affected.

5. **`find_similar()` gains two optional parameters:** `keyword_filter` and `exclude_ids`. Backward-compatible — existing callers pass neither.

6. **Four new migrations (6–9)** add columns to primitive tables and `pending_evaluations`, and create two new tables. Run automatically on first startup after upgrade.

7. **`EvaluatorResponse` gains `evaluator_prompt` computed field.** Both `rendered_prompt` and `evaluator_prompt` appear in JSON serialisation with identical values. The alias is deprecated — use `rendered_prompt`. Removal in v1.3.0.

8. **`submit_evaluation()` now accepts callback JWT from Authorization header** as fallback (with deprecation warning). Body remains the primary path.

9. **`composition_fitness` dict gains `mean_fitness`, `pool_match`, `task_type` fields.** Additive.

10. **New MCP tool: `agency_update_primitives`.** Additive — tool count increases from 8 to 9.

11. **`agency_status` response may include `version_update_available`, `announcements`, `primitives_update_available`.** Additive.

12. **New CLI command: `agency primitives import <path>`.** Additive.

13. **Starter CSV gains columns:** `parent_ids`, `generation`, `created_by`. Existing CSV parsers that ignore unknown columns are unaffected. Run `agency primitives update` after upgrade.

14. **New dependency: `packaging>=21.0`.** Required for version comparison in status file notifications.
