---
name: agency-dispatch
description: >
  Use instead of dispatching-parallel-agents or subagent-driven-development
  when Agency is configured. Activates when user asks to dispatch subagents
  for tasks in a plan.
---

# Agency Dispatch

## Step 0 — Check Agency availability

```bash
AGENCY_URL=$(python3 -c "
import tomllib, os
with open(os.path.expanduser('~/.agency/agency.toml'), 'rb') as f:
    cfg = tomllib.load(f)
print(f\"http://{cfg['server']['host']}:{cfg['server']['port']}\")
" 2>/dev/null)

curl -sf "$AGENCY_URL/health" > /dev/null || AGENCY_URL=""
```

If `AGENCY_URL` is empty, fall back to standard superpowers:dispatching-parallel-agents with a notice: "Agency is not reachable — falling back to standard dispatch."

## Step 1 — Extract tasks from the plan

Read the current plan file. For each numbered task block, extract:
- `external_id`: task number as a string (e.g. `"task-01"`)
- `description`: natural language description of what the task does
- `skills`: technology names or domain terms mentioned (e.g. `["python", "fastapi"]`)
- `deliverables`: output file paths mentioned

## Step 2 — Send batch assignment request

```bash
AGENCY_JWT="$(cat "${AGENCY_TOKEN_FILE:-$HOME/.agency-superpowers-token}")"
PROJECT_ID="${AGENCY_PROJECT_ID:?Set AGENCY_PROJECT_ID}"

PACKET=$(curl -sf -X POST "$AGENCY_URL/projects/$PROJECT_ID/assign" \
  -H "Authorization: Bearer $AGENCY_JWT" \
  -H "Content-Type: application/json" \
  -d '<tasks JSON from step 1>')
```

If the response is 503 with `primitive_store_empty`, stop and tell the user:
"Agency has no primitives installed. Run 'agency primitives install' before dispatching."

## Step 3 — Store agency_task_ids

Parse `$PACKET`. Hold in context: a mapping of `external_id → {agency_task_id, agent_hash}`.

## Step 4 — Dispatch subagents

For each task, call the Task tool with this prompt structure:

```
[rendered_prompt from packet — copy VERBATIM, do not summarise or rewrite]

## Plan context
[task-specific content from the plan: exact file paths, shell commands, test names, commit conventions]

## Constraints
- Work only on the files listed above
- Do not touch code outside your scope
- Return a summary of what you implemented and the result of running tests
```

## Step 5 — Evaluation

After each subagent returns, for each completed task:

```bash
EVALUATOR_RESP=$(curl -sf "$AGENCY_URL/tasks/$AGENCY_TASK_ID/evaluator" \
  -H "Authorization: Bearer $AGENCY_JWT")
EVALUATOR_PROMPT=$(echo "$EVALUATOR_RESP" | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['evaluator_prompt'])")
CALLBACK_JWT=$(echo "$EVALUATOR_RESP" | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['callback_jwt'])")
```

Dispatch an evaluator subagent with `$EVALUATOR_PROMPT`. Post the result:

```bash
curl -sf -X POST "$AGENCY_URL/tasks/$AGENCY_TASK_ID/evaluation" \
  -H "Authorization: Bearer $CALLBACK_JWT" \
  -H "Content-Type: application/json" \
  -d "{\"output\": \"<evaluator output>\"}"
```
