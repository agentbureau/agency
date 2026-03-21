# Getting Started with Agency

Agency is a prompt composer. It builds specialised AI agents from primitives — small, reusable building blocks — so that each task gets an agent tailored to it, rather than a generic LLM.

## The 3-step workflow

1. **Assign** — call `agency_assign` with a task description. Agency selects primitives and composes an agent. You get back a `rendered_prompt`.
2. **Execute** — adopt the `rendered_prompt` as your operating instructions and do the work.
3. **Evaluate** — call `agency_evaluator` to get an evaluation prompt, assess your own output against it, then call `agency_submit_evaluation` with the result.

This loop is how Agency learns. Evaluations feed back into primitive selection, so compositions improve over time.

## What are primitives?

Agency composes agents from three types of primitive:

- **Role components** — capabilities and expertise (e.g. "technical writer," "code reviewer")
- **Desired outcomes** — success criteria for the task (e.g. "output is actionable," "covers edge cases")
- **Trade-off configurations** — decision rules for resolving tensions (e.g. "favour thoroughness over speed")

A starter set ships with Agency. The pool grows as you use it — the evolver proposes new primitives based on evaluation patterns.

## What makes this different from just using an LLM?

- **Performance history** — Agency tracks which compositions worked well for which task types
- **Feedback loop** — evaluations improve future compositions automatically
- **Separation of concerns** — "what should this agent be?" is distinct from "do the work"

In testing, Agency-composed agents scored 55/60 vs 26/60 for general-purpose prompts on a 12-dimension evaluation.

## Try it now

Want to see it in action? Here is a simple demo:

1. Call `agency_assign` with a task like: `{"external_id": "demo-1", "description": "Write a concise summary of what Agency does in 3 sentences."}`
2. Look at the `rendered_prompt` in the response — that is your composed agent
3. Execute the task following that prompt
4. Call `agency_evaluator` with the `agency_task_id` from the assign response
5. Evaluate your output, then call `agency_submit_evaluation`

## Make Agency your default

Add this to your project's `CLAUDE.md` to route all work through Agency:

```
Always use agency_assign before spawning subagents or doing work directly.
```

This ensures every task gets a tailored composition rather than a generic prompt.

## Customise composition rules

Agency's composition behaviour is controlled by `~/.agency/composition-rules.csv`. You can edit it conversationally — run `/agency-composition-config` for a guided walkthrough.

Changes to the composition config take effect on the next `agency_assign` call (no restart needed).

## Quick reference

| Tool | Purpose |
|---|---|
| `agency_assign` | Compose agents for tasks, get prompts |
| `agency_evaluator` | Get evaluation prompt + callback JWT |
| `agency_submit_evaluation` | Submit evaluation results |
| `agency_get_task` | Check task state and composition |
| `agency_list_projects` | List all projects |
| `agency_create_project` | Create a new project |
| `agency_status` | Instance health and task progress |
