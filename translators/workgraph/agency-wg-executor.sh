#!/usr/bin/env bash
set -euo pipefail

PROMPT_DIR=".workgraph/agency-prompts"
AGENCY_CONFIG="${AGENCY_STATE_DIR:-$HOME/.agency}/agency.toml"
AGENCY_URL=$(python3 -c "
import tomllib
with open('$AGENCY_CONFIG', 'rb') as f:
    cfg = tomllib.load(f)
print(f\"http://{cfg['server']['host']}:{cfg['server']['port']}\")
")
AGENCY_JWT="$(cat "${AGENCY_TOKEN_FILE:-$HOME/.agency-workgraph-token}")"

PROMPT="$(cat "$PROMPT_DIR/$WG_TASK_ID.prompt")"
AGENCY_TASK_ID="$(cat "$PROMPT_DIR/$WG_TASK_ID.task_id")"

# Heartbeat loop — required to prevent Workgraph killing the agent
(while true; do sleep 90; wg heartbeat "$WG_AGENT_ID" 2>/dev/null; done) &
HEARTBEAT_PID=$!
trap "kill $HEARTBEAT_PID 2>/dev/null || true" EXIT

# Run Claude with the Agency-composed prompt
claude --print --model "${WG_MODEL:-claude-sonnet-4-6}" "$PROMPT"
EXIT_CODE=$?

kill $HEARTBEAT_PID 2>/dev/null || true

if [ $EXIT_CODE -eq 0 ]; then
  wg done "$WG_TASK_ID"

  # Fetch evaluator and run it
  EVALUATOR_RESP=$(curl -sf "$AGENCY_URL/tasks/$AGENCY_TASK_ID/evaluator" \
    -H "Authorization: Bearer $AGENCY_JWT")
  EVALUATOR_PROMPT=$(echo "$EVALUATOR_RESP" | python3 -c \
    "import sys,json; print(json.load(sys.stdin)['evaluator_prompt'])")
  CALLBACK_JWT=$(echo "$EVALUATOR_RESP" | python3 -c \
    "import sys,json; print(json.load(sys.stdin)['callback_jwt'])")

  EVAL_OUTPUT=$(claude --print --model "${WG_MODEL:-claude-sonnet-4-6}" "$EVALUATOR_PROMPT")

  curl -sf -X POST "$AGENCY_URL/tasks/$AGENCY_TASK_ID/evaluation" \
    -H "Authorization: Bearer $CALLBACK_JWT" \
    -H "Content-Type: application/json" \
    -d "{\"output\": $(echo "$EVAL_OUTPUT" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}"
else
  wg fail "$WG_TASK_ID" --reason "claude exited $EXIT_CODE"
fi
