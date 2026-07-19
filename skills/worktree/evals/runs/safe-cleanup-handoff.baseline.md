# Parallel Worktree Cleanup Runbook

## 1. Establish the authoritative inventory

Run from the primary checkout:

```bash
repo=/Users/kien.ha/Code/vietnam
git -C "$repo" worktree list --porcelain
git -C "$repo" branch -vv
git -C "$repo" status --short --branch --untracked-files=all
```

Record each worktree’s:

- Absolute path
- HEAD commit
- Checked-out branch or detached state
- `locked` or `prunable` annotation
- Owning task or agent, if known

Treat the primary checkout as a worktree too. Never remove it.

## 2. Inspect every existing worktree

For each path that still exists:

```bash
git -C "/absolute/worktree/path" status --short --branch --untracked-files=all
git -C "/absolute/worktree/path" diff --stat
git -C "/absolute/worktree/path" diff --cached --stat
git -C "/absolute/worktree/path" log -1 --oneline --decorate
```

Classify it as:

| State | Cleanup decision |
|---|---|
| Tracked modifications, staged changes, or untracked files | Preserve the worktree and branch |
| Clean, but task ownership or completion is uncertain | Preserve until the owner confirms |
| Clean and task completed | Worktree may be removed after branch disposition is decided |
| Path missing but still registered | Investigate as stale metadata; do not recreate or delete files |
| Locked | Preserve unless the reason for the lock is understood and removal is explicitly approved |

A dirty worktree must not be force-removed, reset, restored, cleaned, stashed, committed, or folded into another task. “Unrelated” edits are still user data.

## 3. Verify the missing registered path

First confirm both the registration and filesystem state:

```bash
git -C "$repo" worktree list --porcelain
test -e "/absolute/missing/path"
git -C "$repo" worktree prune --dry-run --verbose
```

Interpretation:

- If the directory is genuinely absent and the dry run identifies its registration as prunable, only administrative metadata is stale.
- If the entry is locked, it may represent an intentionally offline or temporarily unavailable worktree. Do not unlock or prune it without confirmation.
- If the path exists but is inaccessible, mounted elsewhere, or has moved unexpectedly, stop and investigate. Do not treat it as stale.
- Do not manually delete files under `.git/worktrees`; use Git’s worktree commands when cleanup is later authorized.

After explicit cleanup authorization, stale metadata can be removed with:

```bash
git -C "$repo" worktree prune --verbose
```

Run the dry run immediately beforehand. `git worktree prune` removes stale worktree administration records; it does not delete the associated feature branch. Do not confuse it with `git remote prune` or `git fetch --prune`, which concern remote-tracking references.

## 4. Handle the dirty worktree

Leave the dirty worktree registered and untouched.

Record:

```bash
git -C "/absolute/dirty/path" status --short --branch --untracked-files=all
git -C "/absolute/dirty/path" diff --stat
git -C "/absolute/dirty/path" diff --cached --stat
```

Report the branch, change counts, and whether untracked or staged files exist. Do not expose file contents unless needed. Cleanup requires the edits’ owner to commit, relocate, discard, or otherwise resolve them explicitly.

Never use `git worktree remove --force` merely to bypass dirtiness.

## 5. Handle the clean pushed-but-unmerged branch

Confirm local and remote identities without changing local refs:

```bash
git -C "$repo" rev-parse "refs/heads/<feature-branch>"
git -C "$repo" ls-remote --exit-code --heads origin "<feature-branch>"
```

If GitHub CLI is configured, check the integration state:

```bash
gh pr view "<feature-branch>" \
  --json state,mergedAt,mergeCommit,url,baseRefName,headRefName
```

A clean worktree and a pushed branch are separate concerns:

- The clean worktree may be removed when no task still needs that checkout.
- The local and remote branches must remain while the work is unmerged, unless abandonment is explicitly authorized.
- Removing a worktree does not merge or delete its branch.
- A pushed commit is recoverable, but “recoverable” is not permission to delete an unmerged branch.

When authorized, remove only the clean worktree:

```bash
git -C "$repo" worktree remove "/absolute/clean/worktree/path"
```

Then verify that the feature branch remains:

```bash
git -C "$repo" show-ref --verify "refs/heads/<feature-branch>"
git -C "$repo" ls-remote --exit-code --heads origin "<feature-branch>"
```

## 6. Delete branches only under a separate decision

Before deleting a local branch, ensure it is no longer checked out:

```bash
git -C "$repo" worktree list --porcelain
```

Then verify its merge status against the intended base. Local remote-tracking refs may be stale, so prefer confirmed PR state or current remote evidence.

For a normally merged branch:

```bash
git -C "$repo" branch -d "<feature-branch>"
```

Do not use `-D` simply because `-d` refuses. Squash or rebase merges may make ancestry checks fail even after a PR was merged; require confirmed merged PR evidence and explicit authorization before force-deleting such a local branch.

Remote branch deletion is not part of worktree cleanup. It requires a separate explicit decision:

```bash
git push origin --delete "<feature-branch>"
```

Never delete an unmerged remote branch merely because its worktree is clean or absent.

## 7. Required final verification

After any later authorized cleanup, collect:

```bash
git -C "$repo" worktree list --porcelain
git -C "$repo" worktree prune --dry-run --verbose
git -C "$repo" branch -vv
git -C "$repo" status --short --branch --untracked-files=all
```

For every surviving worktree, repeat:

```bash
git -C "/absolute/worktree/path" status --short --branch --untracked-files=all
```

The final report should include:

- Before-and-after worktree inventory
- Each worktree’s path, branch, HEAD, cleanliness, and disposition
- Confirmation that the dirty worktree and its unrelated edits were preserved
- The missing path and the evidence that its registration was stale
- Any metadata entry pruned, distinguished from files or branches
- The clean feature branch’s local SHA, remote SHA, PR state, and base branch
- Confirmation that an unmerged branch was retained
- Every removed worktree path
- Every deleted branch, with merge evidence and authorization
- Confirmation that the primary checkout’s status was unchanged
- Remaining locks, stale entries, ownership questions, or actions awaiting approval
