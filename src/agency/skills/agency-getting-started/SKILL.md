# Getting Started with Agency

This is an interactive walkthrough. Follow each step in order.

## Step 1 — Try Agency with a sample task

Display this to the user, then wait for their response:

> Using Agency is easy and fits into your workflow with Claude. All you have to do is ask Claude to use Agency when doing any task. For instance:
>
> "Hey Claude, please use Agency to read the Agency specification document, then write me a 2-paragraph summary that 1) explains what Agency is and why I should use it, 2) explains how I use Agency with Claude Code, and 3) gives me some examples of tasks I can use Agency for."
>
> Want to try that? (Y/N)

If the user says Y:

1. Tell the user: "I'm sending that prompt to Agency's assigner now. The assigner reads your task description, selects the best-matching primitives from its library, and composes a specialised agent for this specific task."
2. Call `agency_assign` with the task description from the quoted prompt above.
3. Show the user the composed agent's key sections from the rendered prompt (Role, What success looks like, Trade-offs).
4. Execute the task yourself using the full rendered prompt as your operating instructions.
5. Display the output to the user.

If the user says N, skip to Step 2.

## Step 2 — Try Agency with the user's own task

Display this to the user, then wait for their input:

> Now try it with something you actually need done. Describe your task and I'll send it to Agency's assigner, just like I did with the sample. Be as detailed as possible about what output you want.
>
> Just type: "Claude, please use Agency to compose an agent to do X"

When the user provides their task:

1. Tell the user: "Sending your task description to the assigner now — it will select primitives and compose an agent tailored to this specific task."
2. Call `agency_assign` with the user's task description.
3. Show the user the composed agent's key sections from the rendered prompt.
4. Execute the task yourself using the full rendered prompt as your operating instructions.
5. Display the output to the user.

## Step 3 — Evaluate the output

Display this to the user:

> The final step in Agency is evaluation. When you evaluate an agent's output, Agency learns which compositions work well for which tasks. Over time, this makes compositions better — agents get more precisely tailored to the work. I'll evaluate the output from your task now.

1. Call `agency_evaluator` with the `agency_task_id` from the user's task (Step 2).
2. Evaluate the output against the evaluator prompt's criteria.
3. Call `agency_submit_evaluation` with the evaluation.
4. Show the user the evaluation result and score.

## Step 4 — Close

Display:

> That's all there is to it! We hope you'll find Agency helpful.
>
> **Make Agency your default.** Would you like me to update your project's CLAUDE.md to route all work through Agency automatically? (Y/N)

If Y: Add the following line to the project's CLAUDE.md file:

```
Always use agency_assign before spawning subagents or doing work directly.
```

Then tell the user: "Done — Agency is now your default for all tasks in this project."

If N: Tell the user: "No problem. You can always ask me to set this up later."

Then display:

> **Check your instance** any time with `agency_status` — it shows your projects, task progress, and primitive pool health.
>
> **Re-run this walkthrough** any time with `/agency-getting-started`.
