# Agency

**A self-hosted engine for composing, evaluating, and evolving AI agents.**

Agency treats AI agents not as monolithic system prompts but as composable, evaluable, evolvable entities — structured the way organisations have always structured human work. It decomposes agents into independent primitives (role components, desired outcomes, trade-off configurations), composes them into agents matched to specific tasks, evaluates their performance, and uses the results to improve future compositions.

Agency does not execute tasks. It composes agent descriptions and returns them to a task manager (Claude Code, Superpowers, or any MCP-compatible system) which executes the work. Agency handles composition, evaluation, and evolution; the task manager handles execution.

## Why this exists

Current approaches to commissioning AI agents ignore nearly everything organisations have learnt about getting good work from agents (people). Three problems stand out:

1. **No way to specify subjective trade-offs.** You can tell an agent what to do, but not how to navigate the trade-offs inherent in any real task — speed vs thoroughness, cost vs quality, exploration vs reliability. Agency makes trade-off preferences explicit and controllable through structured trade-off configurations, based on the [Boris methodology](https://vaughntan.org/unpacking-boris) for trade-off articulation.

2. **No inter-deployment memory.** An agent performs a task well or poorly, then starts from zero on the next similar task. Agency records structured performance data across deployments, building a track record for each primitive and composition.

3. **No controlled evolution.** Agent configurations are static — a human writes them, a human edits them. Agency provides mechanisms for mutation, recombination, and selection of agent components, under human-defined fitness criteria.

The underlying model draws on [research into how high-performing R&D teams structure roles under uncertainty](https://journals.sagepub.com/doi/full/10.1177/0001839214557638): roles as modular assemblages of discrete components that can be independently proposed, tested, evaluated, and recombined. Agency applies this same structural logic to AI agents.

## Core concepts

- **Role components** — individual capabilities an agent brings to a task
- **Desired outcomes** — what success looks like, specific enough for an evaluator to grade against
- **Trade-off configurations** — acceptable and unacceptable trade-offs governing how work is done
- **Agents** — compositions of role components + desired outcomes + trade-off configurations, matched to tasks by semantic similarity
- **Evaluators** — specialised agents that grade task output against desired outcomes, building the performance data that drives evolution

## Quick start

```bash
# Install (pipx recommended — keeps agency on PATH across sessions)
pipx install agency-engine

# If you use pip instead, the command is only available while the venv is active
# pip install agency-engine

# Set up
agency init

# Start the server
agency serve

# Verify
curl http://127.0.0.1:8000/health
```

## Usage with Claude Code

Agency registers as an MCP server during `agency init`. Once running, Claude Code can:

1. **`agency_assign`** — compose agents for tasks, receive rendered prompts
2. **`agency_evaluator`** — get evaluation criteria and callback JWT for completed tasks
3. **`agency_submit_evaluation`** — submit structured evaluation results
4. **`agency_list_projects`** — discover available projects
5. **`agency_create_project`** — create new projects
6. **`agency_status`** — check instance health, task progress, primitive counts

The full caller protocol is documented at [docs/integrations/caller-protocol.md](docs/integrations/caller-protocol.md).

## Verify your server is running

```bash
curl http://127.0.0.1:8000/health
# Returns: {"status": "ok", "version": "1.2.1"}
```

## Licence

Code is licensed under the [Elastic License 2.0](LICENSE). You may use, copy, distribute,
and prepare derivative works of the software, but you may not provide it to third parties
as a hosted or managed service.

Written content, specifications, and documentation are licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). You are free to share and adapt them for any purpose, provided you give appropriate credit to Vaughn Tan.
