# Agency — specification v1.0.0
*2026-03-06*

---

## Purpose and scope

Agency is a standalone service for composing, assigning, evaluating, and evolving AI agents. It is released under Elastic License 2.0. This licence permits self-hosting for internal use without restriction. The one thing it does not permit is offering Agency as a managed or hosted service commercially. If you are running Agency for your own organisation's tasks, the licence does not affect you.

Agency does not execute tasks. It composes and assigns agent descriptions; the task manager executes tasks using those descriptions. Agency works with any task management system.

---

## Core concepts

### Primitives

Agency stores three types of primitives independently:

- **Role components** — individual capabilities: the ability to do a specific thing
- **Desired outcomes** — what success looks like for a type of work
- **Trade-off configurations** — acceptable and unacceptable trade-offs governing how work is done

These are stored as independent, uncommitted objects. Pre-composed agents are a cache on top of this primitive store, not the ground truth.

### Agents and actor-agents

An **agent** is a composition of role components + desired outcomes + trade-off configuration. It is a deployable configuration that may exist in the composition cache without being assigned to any task.

An **actor-agent** is an agent that has been assigned to a specific task and is actively performing it.

### Self-similar system

All special-type agents — assigner, evaluator, evolver, agent creator — are first-class agents governed by the same primitive structure as every other agent. None are privileged system components. All accumulate performance history and are subject to selection pressure.

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
| `instance_id`, `client_id`, `project_id` | UUID v7s (provenance) |
| Performance metadata | Former agents it was part of; evaluations received |

### Composition cache

Pre-composed agents on top of the primitive store. Each agent record stores the IDs of its constituent primitives, a content hash of the composition, its permission block, and its performance history. The cache is a performance optimisation; the primitive store is the ground truth.

### Unique identifiers

All IDs are UUID v7: globally unique without coordination, time-ordered.

---

## Integration surface

### Project level

| Direction | Signal | Notes |
|---|---|---|
| IN | Project definition | |
| IN | API key for Agency's LLM calls | |
| IN | Clarification oversight preference | `discretion` or `review` |
| IN | Error notification timeout | Duration before contact is notified |
| IN | Contact email | Designated notification address |
| OUT | Project ID + confirmation | UUID v7 |

### Task level — individual

| Direction | Signal | Notes |
|---|---|---|
| IN | Task description + project ID | |
| OUT | Task agent (markdown) | Task baked in; role components + desired outcomes + trade-off config |
| OUT | Evaluator agent (markdown) | Callback JWT baked in |
| OUT | Task clarification request | Only if oversight preference = `review` |
| IN | Task clarification response | |

### Task level — batch

| Direction | Signal | Notes |
|---|---|---|
| IN | List of task descriptions + project ID | All tasks sent together before execution begins |
| OUT | Assignment packet | Task-to-agent mapping + deduplicated agent definitions |

The batch endpoint is the preferred integration pattern. The calling tool sends all tasks at once before execution begins; Agency returns a packet mapping each task to a composed agent and including all unique agent definitions. Tasks that compose to similar agents (cosine similarity ≥ 0.90) share a single agent definition in the packet.

### Callbacks from field (evaluator → Agency)

| Direction | Signal |
|---|---|
| IN | Full evaluation report + content hash |

Received directly from the evaluator agent (not routed through the task manager). Agency returns a hash of the received payload; the sender verifies the match.

### Evolution oversight

| Direction | Signal |
|---|---|
| OUT | Evolution proposal (changes to desired outcomes or role components requiring human sign-off) |
| IN | Human approval/rejection |

### Admin

| Direction | Signal |
|---|---|
| IN | Primitive ingestion API (CSV or manual) |

---

## Internal agent types

### Assigner

The assigner matches incoming tasks to agent configurations from the composition cache, or composes new configurations from primitives when no suitable cached agent exists. It weighs matches by historical performance. When a task is underspecified, the assigner can request clarification before assigning.

The assigner's trade-off configuration governs when to request clarification versus proceed — from always asking when any criterion is missing to proceeding with a low-confidence flag.

### Evaluator

The evaluator grades completed actor-agent tasks. It is not run inside Agency. It is rendered as a markdown agent description and sent to the task manager alongside the task agent. It runs in the task manager's environment. On task completion it calls back directly to the client's Agency instance.

The callback JWT is baked into the evaluator's markdown at creation time, bound to a specific task. Reports where the task ID in the body does not match the JWT are rejected. Each JWT can be consumed only once. Evaluators accumulate performance history and are subject to selection pressure like any other agent.

### Evolver

The evolver modifies primitives and their configurations. Its mutation strategies are themselves first-class role components stored in the primitive store — not hardcoded system logic. This means the evolver's own behaviour can be evolved.

The evolver targets two dimensions: (1) **level** — individual primitive, composition, or agent; (2) **amount** — minimal, moderate, or maximal change.

Evolution of trade-off configurations may proceed automatically. Evolution of desired outcomes (what is worth pursuing) requires human sign-off, surfaced as an evolution proposal.

### Agent creator

The agent creator expands the primitive store by searching outside the agency for new role components, desired outcomes, and trade-off configurations. Its trade-off configuration specifies search proximity — adjacent domains or unconstrained.

The agent creator, evolver, and assigner form a pipeline: create new primitives → evolve and test configurations → assign to tasks.

### Renderer

The renderer takes role components + desired outcomes + trade-off configurations + task description and produces a single short markdown document. The rendering template is an evolvable parameter.

---

## Evolution mechanism

Primitives carry both a content hash (identity) and a semantic embedding (position in meaning-space). The evolver operates on these two representations differently: content hashes track which version of a primitive was used where; embeddings are the target of mutation operations.

To find better-performing primitives, Agency can run parallel evaluations: N variant agents, identical except for one mutated primitive, run against the same task. The best-performing variant is selected. This is token-intensive and is triggered explicitly by the human or as a scheduled learning run.

---

## Permission model

Every primitive and every composed agent carries a permission block encoding who is authorised to modify it, whether that authorisation is permanent or time-limited, and whether it can be re-delegated. Permissions cascade from project level to agent level to primitive level, with more specific settings overriding less specific ones.

By default, all primitive types are human-only — the evolver cannot modify anything without explicit human delegation.

---

## Authentication

Agency uses JWT tokens for API authentication. The JWT secret is generated at instance initialisation and stored in `agency.toml`.

Task manager JWTs are issued via the `agency token create` CLI command. Evaluator JWTs are task-scoped: generated at evaluator creation time and bound to a specific task. Each evaluator JWT can be consumed only once.

---

## LLM configuration

Agency makes LLM calls only for its own internal operations: task assignment, agent creation, evolver runs, mutation tests, selection runs.

Three configuration fields at instance setup:

| Field | Notes |
|---|---|
| `llm_endpoint` | URL — default Anthropic API; point at local server for local models |
| `llm_model` | Model identifier |
| `llm_api_key` | Credential |

Local models are supported: point `llm_endpoint` at Ollama, LM Studio, or any OpenAI-compatible local server. Agency carries no LLM markup — costs are entirely the user's own.

---

## Error handling

General principle: notify the client contact after a configurable timeout from failure (`error_notification_timeout`, set at project setup).

| Error type | Behaviour |
|---|---|
| LLM call failure | Retry until timeout; notify contact; resume automatically when reachable |
| No agent can be created for task | Notify contact immediately; log for agent creator to address |
| Task clarification timeout | Notify contact after timeout; task remains pending |

---

## Tech stack

| Component | Choice |
|---|---|
| Language | Python 3.11+ |
| API framework | FastAPI |
| Storage | SQLite |
| Vector storage | sqlite-vec (SQLite extension; no additional infrastructure) |
| Embedding model | `sentence-transformers all-MiniLM-L6-v2` (local, CPU-only, no API cost) |
| Deployment | pip install (`agency-engine`) |
