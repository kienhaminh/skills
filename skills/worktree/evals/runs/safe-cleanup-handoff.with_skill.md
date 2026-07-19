# Read-only worktree cleanup runbook

## Goal

Classify every worktree, stale registration, process, database, and branch before any later authorized cleanup. Preserve unknown or unrelated work and retain every unmerged branch.

## Current baseline

Read-only inspection found:

- `/Users/kien.ha/Code/vietnam` is the only registered worktree: `dev@9b75e054422c`, tracking `origin/dev`.
- It is occupied and dirty: `docs/README.md`, `docs/architecture/README.md`, and `docs/design/README.md` are modified.
- `git worktree prune --dry-run --verbose` reported nothing; `.git/worktrees` does not currently exist.
- All local branches are ancestors of the current `dev` snapshot. Nevertheless, retain them:
  - `feat/wiki-publish` tracks a now-gone upstream.
  - `master` is 16 commits ahead of the local `origin/master` snapshot.
  - No fetch was performed, so remote-tracking refs may be stale.
- Runtime topology has one Vietnam Compose container, `vft-postgres`; no process was attributable to this checkout. There are no collision-prone parallel Vietnam Compose stacks currently.

## Inspection sequence

Use `GIT_OPTIONAL_LOCKS=0` for Git inspection commands.

1. Capture the repository-wide inventory:

```bash
GIT_OPTIONAL_LOCKS=0 git status --short --branch
GIT_OPTIONAL_LOCKS=0 git worktree list --porcelain
GIT_OPTIONAL_LOCKS=0 git branch -vv
python3 .codex/skills/worktree/scripts/worktree_matrix.py inventory \
  --repo /Users/kien.ha/Code/vietnam
GIT_OPTIONAL_LOCKS=0 git worktree prune --dry-run --verbose
```

2. For every existing worktree path, record identity and all dirty-state classes:

```bash
GIT_OPTIONAL_LOCKS=0 git -C <path> rev-parse --show-toplevel HEAD
GIT_OPTIONAL_LOCKS=0 git -C <path> symbolic-ref --short -q HEAD
GIT_OPTIONAL_LOCKS=0 git -C <path> status --short --branch
GIT_OPTIONAL_LOCKS=0 git -C <path> diff --name-status
GIT_OPTIONAL_LOCKS=0 git -C <path> diff --cached --name-status
GIT_OPTIONAL_LOCKS=0 git -C <path> ls-files --others --exclude-standard
GIT_OPTIONAL_LOCKS=0 git -C <path> rev-parse \
  --abbrev-ref --symbolic-full-name '@{upstream}'
GIT_OPTIONAL_LOCKS=0 git -C <path> rev-list --left-right --count \
  'HEAD...@{upstream}'
```

Identify the owner, task, and handoff status. Any unknown dirty tree is occupied.

3. For a registered but missing path:

- Check the path and its parent with `stat`; determine whether it moved, its volume is unmounted, or it was actually deleted.
- Preserve the recorded branch and HEAD from `git worktree list --porcelain`.
- Inspect `<common-git-dir>/worktrees/<id>/gitdir`, `HEAD`, and `locked`, if present.
- Run `git branch --contains <HEAD>` and `git tag --contains <HEAD>`.
- Treat `git worktree prune --dry-run --verbose` only as a candidate report. If the checkout moved, a later authorized repair is preferable to pruning.
- Do not prune while ownership, path recovery, or possible uncommitted content remains uncertain; a branch protects committed objects, not missing unstaged files.

4. Verify branch fate separately:

```bash
GIT_OPTIONAL_LOCKS=0 git branch --merged <integration-branch>
GIT_OPTIONAL_LOCKS=0 git branch --no-merged <integration-branch>
git ls-remote --heads origin refs/heads/<feature-branch>
git ls-remote --heads origin refs/heads/<integration-branch>
```

Record the PR state through the hosting service when available. If current ancestry cannot be proved without fetching, mark it unverified and retain the branch.

## Cleanup decision rules

| State | Worktree directory | Metadata | Branch |
| --- | --- | --- | --- |
| Dirty or ownership unknown | Must retain; never use `--force`, reset, clean, stash, or commit it | Retain | Retain |
| Missing but registered | Do not remove a filesystem target | Prune only after recovery checks and separate authorization | Retain until committed reachability is proved |
| Clean, pushed, not merged | Later removal may be safe only when `HEAD` exactly matches the live upstream SHA | Retain until actual removal | Must retain for PR/integration |
| Clean and merged | Later removal candidate | Later prune candidate if stale | Local deletion is a separate authorized action |
| Clean but ahead/unpushed | Retain | Retain | Retain |
| Detached or locked | Retain until reachability and lock ownership are resolved | Retain | Establish a safe ref before later removal |

Worktree removal, metadata pruning, local-branch deletion, and remote-branch deletion are four separate actions. None is implied by another. A `[gone]` upstream is evidence to investigate, not permission to delete.

## Runtime isolation

Before any future test or shutdown:

- Do not start a second collision-prone Compose stack with the same project name or ports.
- Give every concurrently tested worktree a distinct database name ending in `_test`, such as `vietnam_v3_publish_test`.
- Attribute processes by PID, command, and working directory. Only a process whose working directory belongs to the exact worktree may later be stopped.
- Do not stop shared or unrelated containers during worktree cleanup.

## Final evidence

Return one row per worktree:

```text
path | branch@HEAD | dirty | changed files | command:exit | log | blocker
```

Add:

- Live upstream SHA, ahead/behind counts, PR/merge status, owner, and disposition.
- Exact stale metadata reported by `git worktree prune --dry-run --verbose`.
- Remaining worktree matrix and all retained branches.
- Process, Compose project, port, and `_test` database ownership.
- Prior task verification: `pnpm --filter server test`, integration-test status for `pnpm --filter server test:int`, and `pnpm --filter web type-check`. State explicitly that `apps/web` has no unit-test script.
- At most three findings: first diverging mechanism, unavailable check, and remaining risk.

Nothing was executed; no repository, Git metadata, process, database, or remote state changed.

<oai-mem-citation>
<citation_entries>
MEMORY.md:1-3|note=[Used repository source precedence and live recheck guidance]
</citation_entries>
<rollout_ids>
</rollout_ids>
</oai-mem-citation>
