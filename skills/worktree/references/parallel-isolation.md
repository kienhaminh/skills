# Parallel isolation

Use this checklist whenever two or more worktrees execute code concurrently, including builds,
tests, servers, containers, migrations, or debugging.

| Resource | Safe rule | Collision signal |
| --- | --- | --- |
| Branch | Use one branch in one worktree | Git refuses checkout or edits appear in the wrong task |
| Dependencies | Install per worktree; share only download/content stores | Generated modules or lock state change under another run |
| Env | Keep one uncommitted env file per worktree | A run reaches the wrong service or credential set |
| Ports | Allocate a non-overlapping range per slot | `EADDRINUSE`, requests reach another checkout |
| Database | Use a disposable database/schema per worktree | Tests truncate or migrate another run's data |
| Containers | Set a unique Compose project name | Containers are recreated or stopped by another run |
| Build cache | Keep writable framework caches per worktree | Stale bundles, invalid manifests, intermittent compile errors |
| Test output | Separate coverage, snapshots, screenshots, and reports | Files overwrite each other or Git becomes dirty unexpectedly |
| Logs/temp | Use a unique directory per worktree | Evidence is interleaved or cleanup removes another run's files |
| External APIs | Use isolated tenants, fixtures, or read-only calls | Duplicate jobs, rate limits, or irreversible shared mutations |

## Allocate resources

Create a small allocation table before launching long-lived or stateful commands:

```text
slot  worktree                 api   web   database             compose
0     /abs/repo-wt/feature-a   8100  3100  app_test_a           app-a
1     /abs/repo-wt/feature-b   8200  3200  app_test_b           app-b
```

Use the application's real environment variable names. Pass per-worktree values with
`worktree_matrix.py run --slot-env KEY=<template>`; templates may use `{slot}`, `{name}`,
`{port_offset}`, `{path}`, `{branch}`, and `{head}` and are passed without shell evaluation. Confirm
health endpoints return the expected branch or build when possible.

For database tests, preserve the repository's safety suffix and guard conventions. Never point a destructive test harness at a development, shared, staging, or production database. Apply migrations independently to each disposable database.

Before parallel Docker Compose runs, inspect the file for fixed `container_name` values, fixed host ports, named volumes, and external networks. A unique project name, for example `docker compose -p <unique-name> ...`, does not isolate explicitly fixed names or ports. When those exist, share one safe dependency with separate databases/schemas, create an isolated override, or run serially; do not silently reuse the colliding stack.

## Diagnose parallel-only failures

1. Preserve the failing worktree log and exact allocation.
2. Re-run the same command alone in the same worktree.
3. If it passes alone, test one shared resource at a time: ports, database, container project, writable cache, temp path, then CPU or memory pressure.
4. If it fails alone, debug it as a worktree-local code or environment failure using the repository's debugging guide.
5. Report the first diverging resource or mechanism, not merely that concurrency was involved.
