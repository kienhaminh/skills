---
name: worktree
description: Coordinate multiple Git worktrees with explicit ownership and isolated runtime state. Use when agents create, inspect, test, debug, run services in, compare, or clean concurrent worktrees, especially when branches, ports, env, databases, containers, caches, or logs could collide.
---

# Worktree

Treat every worktree as one attributable environment: absolute path, branch or commit, owner, purpose, and mutable-resource allocation.

## Keep these invariants

- Read repository instructions before acting. For this repository, use `docs/TESTING.md`, `docs/DEBUG.md`, and `docs/plans/tech-debt.md` for supported commands and known failures.
- Recheck path, branch, HEAD, upstream, and dirty state immediately before editing, testing, committing, pushing, integrating, or removing.
- Assign one branch and one worktree to one agent. Never share a writable checkout or generated output.
- Treat an unknown dirty worktree as occupied; preserve its changes and establish ownership.
- Isolate every mutable resource. Share only proven read-only or content-addressed caches.
- Refuse concurrent mutation of an external service when no namespace or disposable fixture isolates it.
- Keep merge, rebase, commit, push, branch deletion, and integration with the coordinator unless the user explicitly requests them.

Read [parallel-isolation.md](references/parallel-isolation.md) before running servers, containers, migrations, database tests, or stateful debugging concurrently.

## Inspect and create

```bash
git status --short --branch
git worktree list --porcelain
git branch -vv
python3 <skill-dir>/scripts/worktree_matrix.py inventory --repo <repo>
```

Before creating a worktree:

1. Verify the base branch or commit, unique `codex/<task-slug>` branch, and unused absolute path.
2. Follow the repository's location convention. Use `<repo>/.worktrees` only when ignored; otherwise prefer a sibling path.
3. Run `git worktree add -b <branch> <path> <base>`.
4. Audit ignored or untracked prerequisites because new worktrees contain only committed files. Deliberately recreate or copy needed lockfiles, env files, fixtures, and local helpers without staging secrets.
5. Install dependencies per worktree, then inventory again.

Never reuse a dirty path, attach one branch twice, nest under an unignored directory, or share writable dependencies.

## Delegate

Give each agent exactly one worktree and bounded scope. Include absolute path, branch, verified HEAD, owned files or subsystem, forbidden scope, checks, and handoff contract. Send a complete task brief, not the parent conversation. Keep shared integration surfaces under one owner.

## Run concurrently

Run the same command across explicitly selected registered worktrees:

```bash
python3 <skill-dir>/scripts/worktree_matrix.py run \
  --repo <repo> \
  --worktree <path-a> \
  --worktree <path-b> \
  --max-parallel 2 \
  -- <supported-command>
```

The runner writes per-worktree logs and `summary.json`, and exports `WORKTREE_SLOT`, `WORKTREE_NAME`, and `WORKTREE_PORT_OFFSET`. Map these to real application variables. For different commands or long-running services, use one tracked session per worktree and stop only its process group.

Attribute every result to path and HEAD. If failure occurs only in parallel, preserve evidence and rerun that worktree alone before blaming code; then vary one shared resource at a time.

## Return compact evidence

Store full logs, screenshots, and reports as files. Return one row per worktree:

```text
path | branch@HEAD | dirty | changed files | command:exit | log | blocker
```

Default to 1,000 words or fewer. Use one matrix and parameterized command templates instead of repeating per-worktree scripts. Name package-scoped checks and unavailable test surfaces; in this repository, include server tests, web type-check, and the fact that web has no unit-test script. Add at most three findings: first diverging mechanism, unavailable check, and remaining risk. Do not paste full logs unless requested.

Before returning a plan, explicitly confirm its topology: no collision-prone Compose stacks, distinct per-worktree `_test` databases, and only processes owned by the exact worktree may be stopped. For cleanup, show `git worktree prune --dry-run` on one line. For a read-only plan, end with: `Nothing was executed; no repository, Git metadata, process, database, or remote state changed.`

## Clean up

Inventory again, stop only processes owned by the exact worktree, and inspect its status. Remove only a clean worktree whose branch fate is established as merged, safely retained upstream, or explicitly disposable. Never use `--force` for dirty or unknown changes. Run `git worktree prune --dry-run` before authorized pruning. Treat worktree removal, pruning, and branch deletion as separate scoped actions. End with the remaining worktree matrix and retained branches.
