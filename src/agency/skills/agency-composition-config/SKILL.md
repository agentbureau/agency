# Agency Composition Config

Edit `~/.agency/composition-rules.csv` to control how Agency composes agents.

## CSV schema

| Column | Type | Description |
|---|---|---|
| `agent_type` | string | Which functional agent this rule applies to: `assigner`, `evaluator`, `evolver`, `agent_creator` |
| `rule` | string | Natural language rule matched by embedding similarity against task descriptions |
| `max_role_components` | integer | Maximum role component primitives to include |
| `max_desired_outcomes` | integer | Maximum desired outcome primitives to include |
| `max_trade_off_configs` | integer | Maximum trade-off configuration primitives to include |
| `all_projects` | boolean | `true` if this rule applies to all projects, `false` if scoped |
| `project_ids` | string | Pipe-delimited project UUIDs (e.g. `id1\|id2`). Only used when `all_projects` is `false` |

## Read current config

```bash
cat ~/.agency/composition-rules.csv
```

Or ask: "Show me my current Agency composition rules."

## Modify rules

To **add** a rule, describe what you want:
- "For code review tasks, limit to 3 role components and 2 trade-off configs"
- "Add a rule for the evaluator that emphasises thoroughness over speed"

To **update** a rule, reference it by its rule text or agent type:
- "Change the assigner rule about code review to allow 4 role components"

To **remove** a rule:
- "Remove the evaluator rule about thoroughness"

## Project scoping

Rules can apply to all projects or specific ones. When scoping to specific projects:

1. First, check available projects: call `agency_list_projects`
2. Use the returned project IDs (UUIDs) in the `project_ids` column
3. Separate multiple IDs with pipes: `id1|id2|id3`
4. Set `all_projects` to `false`

**Always validate project IDs** by calling `agency_list_projects` before writing them to the CSV. Invalid IDs are silently ignored at composition time.

## When changes take effect

The composition config is a **watched file**. Changes take effect on the next `agency_assign` call — no server restart needed.

## Example row

```csv
agent_type,rule,max_role_components,max_desired_outcomes,max_trade_off_configs,all_projects,project_ids
assigner,"For code review tasks, favour precision and security expertise",3,2,2,true,
```
