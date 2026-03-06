# Agency project — Claude instructions

## Session start (mandatory)

At the start of every session in this repo, read both of the following files before responding to anything:

1. `agency-project-conventions.md` — file locations, public/private rules, GitHub release workflow, key facts
2. `~/.claude/projects/-Users-vaughntan-agency/memory/MEMORY.md` — current version, pending tasks, open questions

Confirm awareness of:
- Current release version and tag
- Next version and where its PRD lives
- Any pending tasks from the last session
- File location rules (what goes public vs private, where Obsidian is source of truth)

---

## Workflow patterns

- **Comparing diverged remote vs local:** use `git ls-tree -r --name-only HEAD` and `origin/main` for file lists, then loop with `git log -1 --format="%ad"` per file for last-modified dates — produces a clean table before deciding to force-push.
- **Session-start context:** CLAUDE.md is the authoritative instruction mechanism; MEMORY.md and `agency-project-conventions.md` are the content stores it points to. Both must exist and stay in sync.
- **After any repo state change** (push, force-push, file moves): update both MEMORY.md and `agency-project-conventions.md` immediately so they stay in sync.
