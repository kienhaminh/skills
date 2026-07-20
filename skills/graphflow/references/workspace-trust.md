# Workspace trust — Least Privilege + Two-Phase Commit

A worktree reduces filesystem collision; it does not by itself prove scope, preserve Git refs, protect the control plane, or verify the result. Trust only coordinator-observed state.

## Boundary

Before dispatch, the coordinator binds each executor `workspace.ref` to `runtime/workspaces.json` and verifies:

- same Git common directory as the requested repository;
- exact registered path, mode, branch, base SHA, HEAD, and clean state;
- unique slot, port offset, database suffix, compose project, cache, and log allocations;
- worker write/artifact/decision scope, authority grants, protected workflow files, and mutable Git control files (index, config, hooks, info, HEAD, refs).

Never put credentials, environment values, or process arguments in the registry or progress stream. A worker may edit only its registered worktree and declared write scope. It may not change HEAD, branch, shared refs, graph/runtime/memory/integrity state, executor resources, prototype locks, or attestations. Directory inventory, symlink rejection, byte restoration, and quarantine cover newly created as well as pre-existing protected files.
Apply [Primary checkout guard](checkout-guard.md): snapshot the coordinator checkout before dispatch and fail closed on any later change. Declared write ownership applies inside the registered worktree only; it never makes a primary-checkout mutation trusted.
Changed symlinks fail closed because a path-level scope cannot prove their eventual write target; supporting them requires a future explicit contract extension rather than an agent exception.

A worktree is not an OS sandbox. Treat a `command` executor as trusted, digest-locked coordinator code; audit every argv/resource and grant network/credentials separately. Run untrusted or high-risk tools inside an explicitly authorized container/sandbox with scoped mounts. Agent executors still use the declared Codex sandbox, and post-run scope verification remains mandatory.

## Two-phase handoff

1. **Prepare:** provision from a pinned SHA; snapshot HEAD/branch/ref digest; run the node; restore/quarantine control-plane mutations; recompute changed-file manifest; reject outside/forbidden paths.
2. **Validate:** run coordinator-owned acceptance checks against that exact workspace.
3. **Commit:** recompute the manifest immediately before staging; reject stale/TOCTOU changes; create an idempotent local checkpoint commit under coordinator identity.
4. **Integrate:** cherry-pick dependency checkpoints in topological order into the single integration workspace. Abort a conflicted cherry-pick and block; never auto-resolve outside the integration contract.
5. **Verify:** create a detached verifier worktree at the accepted integration checkpoint and rerun every critical oracle there. High integrity additionally requires matching protected external provenance.

Workers never commit, push, or mutate the registry. Internal checkpoints are coordinator recovery objects; public commit/push/PR uses the separate authority-gated Ship delivery broker after verification.

## Parallel progress

Parallel nodes need disjoint ownership and distinct workspace refs. The runner serializes shared paths and waits for the full frontier before applying graph/memory transitions. Each node runner freezes its own progress snapshot while peer telemetry may advance; after validation, only the coordinator writes that node's terminal `accepted`/`independently_verified` snapshot. Completion requires both the observed trust phases and this terminal snapshot, so peer progress does not create a false tamper signal or an acceptance shortcut.

Dashboard `/progress.json`, `/workspaces.json`, and `/checkout.json` are read-only projections. They exclude prompts, reasoning, environment, credentials, full logs, file contents, repository roots, and confirmation answers.

## Recovery + cleanup

- Resume reconciles a durable result and its checkpoint idempotently. A changed manifest after scope verification is rejected.
- A waiting executor must leave the workspace unchanged; partial work cannot cross a confirmation boundary.
- Failed dirty worktrees are retained for inspection and never auto-discarded.
- Cleanup is allowed only for Graphflow-owned, clean worktrees proven `integrated`, `verified`, or `rejected-disposable`:

```bash
python3 <skill-dir>/scripts/workspace_manager.py inspect <workflow-dir>
python3 <skill-dir>/scripts/workspace_manager.py cleanup <workflow-dir> \
  --repo-root <repo> --workspace-ref <ref>
```

Use the project `worktree` skill when `operations` contains `worktree-management`; Graphflow's workspace manager remains the runtime source of truth.
