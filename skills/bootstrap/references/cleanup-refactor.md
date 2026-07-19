# Cleanup and restructuring

Use this decision pattern whenever bootstrap work includes deleting, consolidating, moving, or replacing existing resources.

Lead with **GQM** for measurable outcomes, a **Software Reflexion Model** for intended-versus-actual dependencies, and **Characterization Tests** for behavior preservation.

## Build an evidence ledger

Inventory each candidate across these surfaces:

- source imports, exports, dynamic loading, reflection, plugins, and runtime discovery;
- manifests, workspaces, path aliases, build graphs, generators, and lockfiles;
- tests, fixtures, snapshots, seeds, migrations, and data loaders;
- CLI commands, scripts, hooks, CI, deployment, containers, and scheduled jobs;
- docs, examples, API contracts, external consumers, and operator procedures;
- assets referenced through filenames, URLs, templates, or database values.

Record a disposition and evidence:

| Disposition | Meaning | Required action |
| --- | --- | --- |
| Keep | Current and owned | Route it from the source of truth |
| Migrate | Needed through a new boundary | Move consumers before removal |
| Archive | Historical evidence worth retaining | Isolate and label non-authoritative |
| Delete | Superseded or generated, with no consumers | Remove references and resource together |
| Unknown | Ownership or runtime reachability unclear | Preserve and investigate or ask |

Treat `rg` as one input. Dynamic imports, reflection, deployment config, external clients, and persisted paths may produce no static references.

## Delete safely

1. Resolve exact targets; avoid broad globs and recursive roots.
2. Confirm the working tree and preserve unrelated edits.
3. Prefer a dedicated commit or recoverable move for material cleanup.
4. Remove consumers, configs, docs, tests, and dependencies in the same bounded change.
5. Reinstall from the lockfile when dependencies change; inspect lockfile drift.
6. Run the narrow affected gate, then the full supported gate.
7. Search again for old names, paths, package IDs, env keys, ports, and commands.

Never infer permission to delete production resources, databases, buckets, secrets, migrations, backups, or user-owned files from a request to clean the repository. Flag generated files that are committed intentionally instead of deleting them by convention.

## Restructure incrementally

State the target boundary before moving files: ownership, public API, allowed dependency direction, and entrypoint. Prefer these patterns:

- **Move then narrow:** preserve exports while relocating internals; reduce the surface after consumers migrate.
- **Adapter seam:** keep a temporary compatibility facade across package or API moves; delete it only after usage reaches zero.
- **Branch by abstraction:** introduce the new interface, migrate callers, switch the binding, then remove the old implementation.
- **Strangler slice:** replace one vertical path at a time when old and new generations must coexist.
- **Characterize then simplify:** pin observable behavior before untangling code with weak coverage.

Keep structural and behavioral changes separate whenever practical. A move should remain reviewable as a move; formatting or feature changes obscure regressions and history.

## Protect repository invariants

During monorepo or source-tree changes, preserve or deliberately migrate:

- application and worker entrypoints;
- package names, exports, workspace membership, and internal versioning;
- TypeScript/Python/module aliases and generated-client paths;
- environment ownership and startup validation;
- schema and migration ordering;
- test discovery, fixtures, coverage inputs, and CI caches;
- container contexts, deployment roots, health checks, and release commands;
- source maps, licenses, attribution, and required notices.

Update the agent entrypoint, architecture owner, runbook, and docs router only after the new tree is executable.

## Completion gate

Require evidence that:

- old and new entrypoints behave as planned during migration;
- public contracts are unchanged or the breaking change is explicit;
- searches find no unintended old references;
- clean install, build, static checks, and relevant tests pass;
- runtime, migration, seed, health, and deployment paths work when in scope;
- docs and examples point only to the current tree;
- deleted resources are listed, justified, and recoverable from version control.
