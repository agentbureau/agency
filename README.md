# Agency

**A self-hosted engine for composing, evaluating, and evolving AI agents.**

## In a nutshell
Agency is a tool for building AI agents on the fly from small, readable, natural-language building blocks. When something about an agent doesn’t work, you fix the specific part that’s broken instead of rewriting the whole thing — and every fix makes every future agent better. It fits into your existing AI coding workflow as a background service you interact with in conversation with Claude Code.

## The problem Agency solves

You have an agent that does reasonable work. Not bad — reasonable. So you rewrite the prompt. You add more instructions. It gets better in one dimension and worse in another. After three rounds, you have a 2,000-word system prompt that is fragile, opaque, and works for one task. Next month, when you need something slightly different, you start over.

Even if you don't handwrite prompts, the problem remains. You use skills, MCP tools, or pre-built workflows to configure the agent. You get reasonable results, and when one specific capability is weak, there is no way to fix just that part. You can tweak settings or swap the whole tool. But you can’t open the agent up and improve the piece that isn't working.

The problem is that a monolithic, non-composable agent is not the right unit of improvement. A monolithic agent has no user-serviceable component parts to individually fix or replace when the agent breaks or needs to be improved.

## Making agents composable

The reason you can't is that your agent isn't made of parts. It's one block of text — or one opaque configuration. When an agent’s analysis is sharp but the recommendations are vague, there's nothing to point at and say "that's the piece that needs to change." So you have to rewrite the whole thing, hope you haven't broken something else that was working, and re-test.

Agency makes the parts real and useable. It composes agents from small but meaningful building blocks — short, readable, natural-language statements called **primitives** — and makes those the unit of storage, evaluation, and improvement. When something doesn't work, you change one primitive. Everything else stays the same.

## Three types of agent primitives

Agency agents are composed from three types of primitives:

1. **Role components** describe capabilities — what an agent can do. "Identify gaps, errors, or inconsistencies in provided content." "Ground abstract arguments in concrete, sensory-level examples." Each one is a single capability, typically one or two sentences, that might be useful across many different kinds of work.
2. **Desired outcomes** describe what success looks like — the shape and quality of a good output. "Return a structured evaluation report with a numeric score and specific improvement recommendations." These are reusable definitions of what "done" looks like for a type of work.
3. **Trade-off configurations** describe decision rules — how the agent should behave when competing values conflict. "When thoroughness and efficiency conflict: prefer thoroughness. Flag the trade-off in the output." These resolve the ambiguities that role components and desired outcomes leave open.

All three types are written in natural language. They are short — role components target 50 to 150 characters. You can look at any individual primitive and immediately understand what it does. You can add new primitives at any time. A bundled primitive extractor skill can pull them from your existing workflows, skills, and sessions.

## How it works in practice

You ask Claude Code to give Agency a task to assign an agent to do: “Ask Agency to compose an agent to review a PRD for issues that would slow down or block implementation. Produce the output as a numbered list of issues ordered by priority.” Agency analyses the task, selects primitives from its pool that fit, and composes a specialised agent from those primitives. 

It sends the agent composition back to your LLM, which despatches the agent to do the work. The review is reasonable — it catches formatting inconsistencies, a few missing section headers. But it reads the spec in isolation. It doesn't check the PRD against the actual codebase. Score: 26 out of 60 on a 12-dimension review scorecard.

The gap is specific: the reviewer needs to be codebase-aware. It should check that API signatures in the spec match the real code, that database operations are valid SQL, that acceptance criteria are testable against what's actually built. With Agency, you can address the specific gap by adding primitives for those capabilities.

You re-run the same task with these new primitives. Agency composes a different agent — one that now includes those codebase-aware review primitives. This time, the review catches a return key mismatch: the PRD specified a field called `similarity`, but the code actually returned `score`. Every relevance check would have silently defaulted to zero, excluding all primitives from every composition. No amount of reading the PRD in isolation would have found this — the reviewer needed to be composed with the right capability. Score: 55 out of 60. 

Those primitives took one sentence each to describe and required no code changes. Agency stored them, composed a better agent, and the scores went up. That evaluation is now in Agency's memory, so the next time any task needs codebase-aware review, Agency knows which primitives worked.

That example is from a real session in which Agency reviewed its own PRD during development of v1.2.3. Four rounds of review by differently composed, tailored Agency agents caught 14 implementation blockers: an unimplementable feature architecture, SQL operations that would silently match nothing, amendment scars where a fix in one section left contradictory text in another. These went undetected by general purpose Claude-spawned agents that were given the same tasks each round. 

Agency works for software development, but its mechanism is general. Agency agents have been composed for writing blog posts, doing research, designing workflows, and generating client memos — any task you can describe with a clearly specified desired outcome, Agency can probably compose a tailored agent for. And you can add primitives to expand Agency’s capabilities too.

## Surgery, not wholesale rewrites

The agent that scored 26 was not bad in every dimension. Its reading comprehension was fine. Its output structure was fine. What was missing was a specific capability — checking specs against real code. In a monolithic prompt, closing that gap means rewriting the whole thing and hoping you don't break what was already working. In Agency, you add one primitive, and leave everything else unchanged. You can verify that the improvement came from exactly the change you made, because it is the only thing that changed.

This compounds. Every primitive you add potentially improves every future agent, not just the current one. Each evaluation teaches Agency which compositions work and which don't. As evaluations accumulate, they create performance data that drives which primitives and compositions get reused, and which get replaced. Agency helps you build an organisational memory of what AI agents work well, and why.

## What Agency learns

Agency stores three layers of knowledge: primitives (the building blocks), compositions (which primitives were assembled for which tasks), and performance (how each composition scored against specific criteria). This is memory *about* agents, not memory *within* them. No single agent carries context forward. The system does.

This lets you trace patterns that monolithic prompts can't reveal. You can ask: "Which role components appeared in my five lowest-scoring review agents?" — and get a list, because Agency tracks that data. You can spot the same missing capability across your lowest-scoring agents and close it with one primitive. The answers live in records Agency can query, not in someone's memory of which prompt version worked last Tuesday.

## What it looks like

Using Agency is simply asking Claude to use Agency to get agents for tasks:

> "Hey Claude, use Agency to compose an agent to read this document and write me a summary that explains the key arguments, identifies any logical gaps, and suggests three improvements."

If you use a task manager/planner (like Superpowers), ask Claude to use Agency with your task manager:

> “Claude, when using Superpowers to plan this implementation, be sure to use Agency to compose agents to do each task.”

When Agency receives a request for an agent, it analyses the task, uses a fast semantic search to compose an agent by choosing from its store of primitives, then hands the composition back to the requester (Claude Code or your task manager). The requester despatches the composed agent to do the work. You can use Agency to assign tasks, execute them, and submit evaluations, all in natural language conversation. Agency’s infrastructure does the work behind the scenes. You never have to touch any of it — no SQL, no config files, no code.

## Quick start

Install Agency:

```bash
pipx install --python python3.13 agency-engine
```

Run the setup wizard, then start the server:

```bash
agency init
agency serve
```

From that point on, everything happens in conversation with Claude. You can run the bundled skill /agency-getting-started to try Agency out for the first time.

<details>
<summary>Install commands and troubleshooting</summary>

```bash
# Install (requires Python 3.13+)
pipx install --python python3.13 agency-engine

# Set up — interactive wizard handles everything
agency init

# Start the server
agency serve

# Verify (optional)
curl http://127.0.0.1:8000/health
# Returns: {"status": "ok", "version": "<your installed version>"}
```

**Python 3.13+ required.** If `pipx` was installed with an older Python (common with Homebrew), the `--python python3.13` flag tells pipx to use the correct interpreter. Run `python3.13 --version` to check. If not available: `brew install python@3.13` (macOS) or see https://www.python.org/downloads/.

**PyPI behind?** Install directly from GitHub: `pipx install --python python3.13 git+https://github.com/agentbureau/agency.git`

</details>

## What Agency is not

Agency is not a runtime for long-running autonomous agents. It doesn’t try to build one agent that can work unsupervised for hours — that’s a different problem. Agency composes small, well-formed agents for small, well-defined tasks on request, and gives them back to the requester — an LLM, a skill being used by an LLM, a pipeline, a human — to despatch. 

This makes Agency a complement to long-horizon agent runtimes, not a competitor. A runtime that spawns short-lived agents can use Agency to compose each one. Agency handles "who should this agent be?" The runtime handles "how do I keep it working?"

<details>
<summary>Integration guides</summary>

Agency works with different task execution systems:

| You are using | Guide |
|---|---|
| **Claude Code** (MCP tools directly) | [Using Agency as an MCP with Claude Code](docs/integrations/using%20agency%20as%20an%20MCP%20with%20claude%20code.md) |
| **Superpowers** (brainstorming, plans, subagent dispatch) | [Using Agency with Superpowers](docs/integrations/using%20agency%20with%20superpowers.md) |
| **Workgraph** (shell-based batch task execution) | [Using Agency with Workgraph](docs/integrations/using%20agency%20with%20workgraph.md) |

Agency was developed to be used with Claude Code — it may work with other LLMs and providers, but your mileage may vary.

</details>

<details>
<summary>MCP tools</summary>

Agency exposes eight tools via the Model Context Protocol:

| Tool | Purpose |
|---|---|
| `agency_assign` | Compose agents for tasks, receive rendered prompts |
| `agency_evaluator` | Get evaluation criteria and callback JWT for completed tasks |
| `agency_submit_evaluation` | Submit structured evaluation results |
| `agency_get_task` | Retrieve task state, composition, and evaluation status |
| `agency_list_projects` | Discover available projects |
| `agency_create_project` | Create new projects |
| `agency_status` | Check instance health, task progress, primitive counts |
| `agency_triage` | Lightweight primitive matching without full composition |

The full requester protocol (assign → execute → evaluate) is documented in the [Claude Code integration guide](docs/integrations/using%20agency%20as%20an%20MCP%20with%20claude%20code.md#caller-protocol).

</details>

## Licence

Code is licensed under the [Elastic License 2.0](LICENSE). You may use, copy, distribute, and prepare derivative works of the software, but you may not provide it to third parties as a paid or otherwise commercial hosted or managed service.

Written content, specifications, and documentation are licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). You are free to share and adapt them for any purpose, provided you give appropriate credit to [Vaughn Tan](https://github.com/arbois).

Install Agency, run a task, evaluate the output, and watch the next agent get better.