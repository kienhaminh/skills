---
name: worktree
description: Coordinate multiple Git worktrees with explicit ownership and isolated runtime state. Use when concurrent agents or tasks create, inspect, test, debug, compare, integrate, or clean worktrees whose branches, ports, databases, containers, caches, or logs could collide.
---

# Coordinate isolated worktrees

Treat each worktree as one attributable environment: absolute path, branch or commit, owner, purpose,
and mutable-resource allocation.

## 1. Inventory before action

Read repository instructions and supported test/debug commands. Recheck path, branch, HEAD, upstream,
and dirty state immediately before any edit, test, commit, integration, or cleanup.

```bash
git status --short --branch
git worktree list --porcelain
git branch -vv
python3 <skill-dir>/scripts/worktree_matrix.py inventory --repo <repo>
```

Treat unknown dirty state as occupied and preserve it. Complete inventory when every worktree has a
branch or detached commit and dirty state, while owner, purpose, and resource allocation are either
proved or explicitly `unknown` with the evidence or decision needed to resolve them.

After inventory, execute only the branches the request needs: **create**, **inspect/compare**,
**run/debug**, **integrate**, or **clean up**. Creation is not a prerequisite for existing worktrees;
cleanup is not a post-step for read-only inspection.

## 2. Create one isolated environment

1. Verify the base ref, unique branch, and unused absolute path.
2. Follow repository conventions when present. Otherwise propose an unused sibling path and a
   task-derived branch, and confirm any choice that changes shared naming or retention policy.
3. Create the worktree with `git worktree add`.
4. Recreate required ignored or untracked prerequisites without staging secrets.
5. When the selected command requires dependencies, use the repository's discovered install command
   inside that worktree; otherwise leave dependency state unchanged. Inventory again.

Assign one writable worktree and branch to one owner. Keep merge, rebase, shared-ref mutation, and
integration with the coordinator unless the user delegates them explicitly.

Complete creation when the registered path, ref, owner, prerequisites, dependency state, and dirty
baseline are proved.

## 3. Isolate mutable resources

Read [parallel-isolation.md](references/parallel-isolation.md) before any concurrent execution,
including builds and tests as well as servers, containers, migrations, or stateful debugging.
Allocate non-overlapping ports, disposable databases or schemas, Compose project names, writable
caches, test outputs, logs, and temp paths.
Share only resources proved read-only or content-addressed. Serialize mutation when an external
service cannot be namespaced safely.

Complete isolation when every mutable resource has one owner or an explicit serial schedule.

## 4. Delegate and run

Give each agent a complete task brief containing absolute worktree path, branch, verified HEAD, owned
scope, forbidden scope, checks, and handoff contract. Pass the task brief rather than parent-chat
history.

Run the same command across selected registered worktrees:

```bash
python3 <skill-dir>/scripts/worktree_matrix.py run \
  --repo <repo> \
  --worktree <path-a> \
  --worktree <path-b> \
  --max-parallel 2 \
  --slot-env APP_PORT={port_offset} \
  --slot-env TEST_DATABASE=app_test_{slot} \
  -- <supported-command>
```

Map slot templates to the application's real variable names. Supported fields are `{slot}`, `{name}`,
`{port_offset}`, `{path}`, `{branch}`, and `{head}`; values are passed directly without shell
evaluation. Prefer an explicit coordinator-owned `--log-dir`. When the helper creates a system-temp
log directory, treat its logs and `summary.json` as retained evidence and return an explicit retention
or removal decision.

Attribute every result to path and HEAD. Preserve a parallel-only failure, rerun that worktree alone,
then vary one shared resource at a time.

Complete execution when each selected worktree has a command result, log path, and classified blocker
or success.

## 5. Return and clean up

Return one compact row per worktree:

```text
path | branch@HEAD | dirty | changed files | command:exit | log | blocker
```

Name relevant checks and unavailable surfaces discovered from the repository. Keep full logs and
screenshots in files; report the first diverging mechanism and remaining risk.

Before cleanup, inventory again and stop only processes attributable to the exact worktree. Present
the exact paths, processes, evidence/log directories, worktree removals, pruning, and branch
deletions, then obtain authorization for each requested destructive action class. Remove a clean
worktree only after its branch is merged, retained upstream, or explicitly disposable. Show
`git worktree prune --dry-run` before authorized pruning and treat evidence removal, worktree removal,
pruning, and branch deletion as separate actions.

The skill is complete when the final matrix accounts for every worktree and retained branch, and no
process or mutable resource owned by another task was changed.
