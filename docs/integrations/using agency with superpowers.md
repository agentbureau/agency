# Agency + Superpowers Integration

How Superpowers skills (brainstorming, writing-plans, subagent-driven-development, executing-plans) work with Agency to compose, dispatch, and evaluate agents.

For general Claude Code MCP setup and tool reference, see [using agency as an MCP with claude code](using%20agency%20as%20an%20MCP%20with%20claude%20code.md).

## How Agency fits into the Superpowers workflow

Superpowers provides the orchestration layer — brainstorming, planning, task decomposition, subagent dispatch, and review. Agency provides the agent composition layer — selecting primitives, composing agents, and recording evaluations. They are complementary:

| Superpowers handles | Agency handles |
|---|---|
| What tasks to do (brainstorming, planning) | What agent to assign to each task |
| How to break work into subtasks | What role components, outcomes, and trade-offs to use |
| Dispatching subagents and reviewing output | Evaluating agent performance and recording results |
| Session orchestration and plan tracking | Inter-deployment memory and primitive evolution |

## Typical workflow

### 1. Brainstorming → task decomposition

Use `superpowers:brainstorming` to explore the problem space and produce a spec. Use `superpowers:writing-plans` to decompose the spec into implementation tasks.

### 2. Assign through Agency

Call `agency_assign` with the tasks from the plan. Agency composes agents by matching task descriptions to its primitive store (role components, desired outcomes, trade-off configurations).

```
agency_assign({
  tasks: [
    { external_id: "task-1", description: "...", skills: [...], deliverables: [...] },
    { external_id: "task-2", description: "...", skills: [...], deliverables: [...] }
  ]
})
```

Each task gets back a `rendered_prompt` (the agent composition) and an `agency_task_id`. The response includes a `task_ids` summary block for quick reference:

```json
{
  "status": "ok",
  "task_ids": [
    {"external_id": "task-1", "agency_task_id": "uuid", "agent_hash": "sha256"}
  ],
  "assignments": { ... },
  "agents": { ... }
}
```

### 2b. Alternative: Assign via CLI (for subagents)

Subagents that cannot call MCP tools can use the CLI instead:

```bash
agency task assign --tasks '[{"external_id": "task-1", "description": "..."}]' --format json
```

Or from a file:

```bash
agency task assign --tasks-file tasks.json --project-id <uuid>
```

The CLI returns the same JSON shape as the MCP tool. Use `agency task evaluator` and `agency task submit` for the evaluation loop.

### 3. Dispatch subagents with Agency prompts

Use `superpowers:subagent-driven-development` or `superpowers:dispatching-parallel-agents` to execute the tasks. Each subagent receives the `rendered_prompt` from Agency as its operating instructions.

The rendered prompt contains:
- **Role** — selected role components (capabilities)
- **Desired outcome** — what success looks like
- **Trade-offs** — how to navigate competing priorities
- **Task** — the specific work to do
- **Output format** — structure and format expectations

### 4. Evaluate via Agency

After each subagent completes, call `agency_evaluator` with the `agency_task_id` to get the evaluation prompt and callback JWT. Run the evaluation (either in the same session or via a review subagent), then call `agency_submit_evaluation` with the result.

Optional structured fields:
- `score` (0–100) — numeric assessment
- `task_completed` (true/false) — completion status
- `score_type` — how to interpret the score (`binary`, `rubric`, `likert`, `percentage`)

### 5. Review with Superpowers

Use `superpowers:requesting-code-review` or `superpowers:verification-before-completion` for the final quality gate. This is separate from Agency's evaluation — Superpowers reviews the work against the plan; Agency evaluates the agent's performance against its composition.

## Key integration points

### Agency assigns, you execute

Agency composes agents but does not execute tasks. When using `subagent-driven-development`, you dispatch the subagents yourself using the rendered prompts from `agency_assign`. Agency has no awareness of your subagent infrastructure.

### One agency_task_id per subagent

Each task assigned through Agency gets a unique `agency_task_id`. Use this (not your `external_id`) when calling `agency_evaluator` and `agency_submit_evaluation`. The `agency_task_id_note` in the assign response reminds you of this.

### Evaluation builds inter-deployment memory

Every evaluation submitted through `agency_submit_evaluation` is recorded against the specific primitive composition that produced the agent. Over time, this builds performance data that Agency uses to improve future compositions. Skipping evaluation means Agency learns nothing from that deployment.

### .agency-project for per-repo defaults

Create a `.agency-project` file in your repo root (`agency project pin`) to set a default project. This takes precedence over environment variables and global config, so different repos can use different Agency projects without changing global state.

## What not to do

- **Don't skip the evaluation loop.** Agency's value comes from recording which compositions work well for which tasks. Assign → execute → evaluate is the full cycle.
- **Don't write your own agent prompts and pass them to Agency.** Agency composes prompts from its primitive store — that's the point. Describe the task; let Agency select the primitives.
- **Don't use `external_id` for evaluation calls.** Always use `agency_task_id` from the assign response.
