---
name: agency-primitive-extraction
description: Use when extracting Agency primitives (role components, desired outcomes, trade-off configurations) from existing skill files, agent descriptions, or prompt documentation, or when authoring new primitives for the Agency starter CSV.
---

# Agency Primitive Extraction

## Overview

Primitives are typed inputs to a rendering pipeline — not prose descriptions. Each type maps to a specific instruction layer in the rendered agent. Write them as machine-readable interface components: self-contained, unambiguous, and parseable without surrounding context.

The three types map to three layers:

| Type | Layer | Grammar pattern |
|---|---|---|
| `role_component` | `ROLE` | Verb phrase, instructional |
| `desired_outcome` | `OUTPUT` | Output schema or structured spec |
| `trade_off_config` | `CONSTRAINTS` / `FAILURE` | Explicit ranked decision rule |

## Structural tests

Apply before accepting any candidate.

**Role component:** "An agent doing this task will ___" — blank is one clear action, no qualifiers.

**Desired outcome:** "The output must include ___" — blank names specific, checkable things (fields, formats, counts).

**Trade-off configuration:** "When forced to choose between ___ and ___: the agent should ___" — all three blanks filled, or it is not a trade-off.

## Extraction process

**Step 1 — Capability claims.** Every "this agent does X" or "you should Y when doing this" → candidate role components. Write as verb phrases.

**Step 2 — Output descriptions.** Format requirements, quality standards, completeness criteria → candidate desired outcomes. Rewrite as structured specs.

**Step 3 — Decision rules.** Words like "prioritise," "prefer," "never," "always," "rather than," "over" → candidate trade-off configurations. "Critical" and "important" flags almost always encode trade-offs.

**Step 4 — Apply structural tests.** Reassign or discard any candidate that fails its type's test.

**Step 5 — Normalise.** Strip narrative scaffolding. "In order to ensure that the output is appropriate" → "Calibrate output for the intended audience."

**Step 6 — Task-type coverage check.** For each desired outcome extracted, identify the task type it serves (build, evaluate, review, research, analyse, debug, plan, synthesise). Check whether the batch covers at least build + evaluate + review for each domain represented. If a domain has outcomes for only one task type, write the missing outcomes before finalising. See "Task-type coverage audit" below.

## Writing conventions by type

**Role components — instructional verb phrases:**
```
❌  Ability to synthesise information from multiple sources
✅  Synthesise information from multiple sources into a single coherent output
```
No vague qualifiers: "carefully," "thoroughly," "appropriately" add noise. Replace with specifics: "rank by confidence," "cite source for each claim."

**Desired outcomes — output schemas:**
```
❌  Produce a clear, concise summary suitable for decision-making
✅  Return a structured summary with: conclusion (one sentence), supporting
    points (bulleted list, max 5), confidence level (high | medium | low)
```
For software-parsed output, write near-JSON schemas. Always include what to do with missing information: `If field is absent: return null. Do not infer.`

**Trade-off configurations — decision rules:**
```
❌  Balance thoroughness with efficiency
✅  When thoroughness and efficiency conflict: prefer thoroughness.
    Flag the trade-off in the output.
```
Structure: *when [condition], do [action], not [alternative].* Include explicit failure/fallback rules for missing inputs and out-of-scope requests.

## Quality criteria

**Atomic** — one thing only. Removing any phrase either loses meaning or reveals two primitives.

**Composable** — works alongside other primitives without conflict.

**General-purpose** — reusable across more than one task type.

**Evaluable** — after a task runs, "did the agent do this?" has a yes/no answer.

**Brief** — role components: 50–150 chars. Over 150 almost always means two capabilities bundled.

## Task-type coverage audit

Desired outcomes describe what the output looks like. The semantic search selects them by matching against the task description. If the pool has desired outcomes only for **building** software but not for **evaluating** or **reviewing** software, a review task in the software domain will be assigned a build-deliverable outcome — the domain matches but the task type is wrong.

**The problem:** domain match ≠ task-type match. A desired outcome for "return an implementation plan with file paths and code" is correct for a build task but wrong for an evaluation task, even though both are in the software domain. The semantic search cannot distinguish task type from domain because both contribute to the embedding.

**Task-type taxonomy:** `build` · `evaluate` · `review` · `research` · `analyse` · `debug` · `plan` · `synthesise`

**Coverage audit (run after any batch extraction or starter CSV update):**

For each domain in the taxonomy that has desired outcome primitives, check whether outcomes exist for at least these task types: build, evaluate, review. These three are the minimum because they represent the most common divergence — a build outcome specifies a deliverable structure, an evaluation outcome specifies an issue-list structure, a review outcome specifies an assessment structure. If any domain has outcomes for only one task type, flag the gap.

**How to write task-type-aware desired outcomes:**

The task type should be implicit in the output schema, not stated as a qualifier. The structural test ("The output must include ___") still applies — the difference is what the blanks contain.

```
Build:     Return an implementation plan with: goal, architecture, numbered tasks with file paths
Evaluate:  Return a severity-ranked issue list with: problem, severity, proposed fix per issue
Review:    Return an assessment with: compliance status per requirement, gaps found, recommendations
Research:  Return a findings summary with: sources consulted, key findings, confidence levels
```

Each describes a different output structure for the same domain. The semantic search matches the right one because the task description for an evaluation contains words like "assess," "flag issues," "feasibility" that align with the evaluation outcome's embedding, not the build outcome's embedding — but only if the evaluation outcome exists in the pool.

## Domain specificity scoring (0–100)

Three factors summed:

**Vocabulary (0–40):** count domain-specific terms in the description.
0 terms → 0 · 1 term → 15 · 2 terms → 25 · 3+ terms → 40

**Task scope (0–40):** would an agent outside a specific domain use this?
Any agent / any task → 0 · Cross-domain professional → 15 · 2–4 specific domains → 25 · Primarily one domain → 40

**Background knowledge required (0–20):**
Not required → 0 · Helpful → 10 · Required → 20

If score > 20: assign at least one domain from the taxonomy.
**Taxonomy:** `software` · `research` · `writing` · `analysis` · `legal` · `strategy` · `science` · `management`

Multiple domains: comma-separated in CSV, stored as JSON array on ingest.

## CSV schema (8 columns)

| Column | Notes |
|---|---|
| `type` | `role_component` \| `desired_outcome` \| `trade_off_config` |
| `name` | Kebab-case slug. Human reference only — not used for identity. |
| `description` | Identity field. SHA-256 of this = content_hash, computed at ingest. |
| `quality` | 0–100. Hand-authored starters: 100. |
| `domain_specificity` | 0–100. Scored by three-factor algorithm above. |
| `domain` | Comma-separated in CSV. Parsed to JSON array on ingest. Empty if ≤ 20. |
| `origin_instance_id` | `00000000-0000-7000-8000-000000000001` for official Agency primitives. |
| `parent_content_hash` | SHA-256 of parent description if evolved from another primitive. Null for originals. |

`content_hash`, `id`, `embedding`, `permission_block`, `instance_id` are computed or assigned at install time — not in CSV.

## Anti-patterns

| Pattern | Problem |
|---|---|
| "Ability to X" | Capability claim, not instruction — fails role component structural test |
| "Be thorough" / "Be careful" | Not evaluable |
| "X and also Y and Z" | Three primitives merged into one — split them |
| "Produce a good output" | Desired outcome with no schema — rewrite with fields |
| "When A happens, be careful" | Trade-off without a decision rule — name what wins |
| Role component > 150 chars | Almost always needs splitting |
| Extracting procedural steps as role components | Steps belong in the skill; the capability belongs in the primitive |
| Domain has desired outcomes for only one task type | Semantic search matches domain, not task type — an evaluation task in the software domain gets assigned a build-deliverable outcome because no evaluation outcome exists. Run the coverage audit after every batch extraction. |

## Reference

Full design philosophy: see the Agency primitives design canon.
Business model context: see the Agency standalone business model document.
