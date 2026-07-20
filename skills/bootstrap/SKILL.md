---
name: bootstrap
description: Bootstrap software repositories from live evidence. Use for initial setup, inherited-codebase rehabilitation, repository mapping, conventions, documentation architecture, safe restructuring, or agent-ready tooling.
---

# Bootstrap a repository

Leave a repository that an unfamiliar contributor can understand, run, test, and change from the
checkout alone.

## 1. Establish the contract

Read the repository instructions, current status, manifests, and executable configuration. Separate
all material statements into:

- **Observed** — proved by a file or command;
- **Requested** — chosen by the user;
- **Proposed** — recommended but still unimplemented.

For material setup or restructuring, read
[scientific-methods.md](references/scientific-methods.md) and define a compact GQM baseline, target,
and stop or rollback condition. Ask only when a missing choice changes architecture, authority, or an
irreversible dependency.

Complete this phase when the objective, constraints, authority, baseline, and acceptance checks are
explicit and proposed state is clearly labelled.

## 2. Map the live checkout

Preserve unrelated work. Inspect manifests, locks, runtime pins, source roots, entrypoints, configs,
CI, tests, data paths, deployment files, and durable docs.

When Python 3 is available, use the inspection helper:

```bash
python3 <skill-dir>/scripts/inspect_codebase.py --root <repo> --format markdown
```

Otherwise inspect the same surfaces with repository-native tools and report the helper as
unavailable; helper availability never narrows the mapping criterion below.

Read [code-navigation.md](references/code-navigation.md), then generate checkout-derived index views:

```bash
python3 <skill-dir>/scripts/index_codebase.py --root <repo> --format ndjson
python3 <skill-dir>/scripts/index_codebase.py --root <repo> --query "<task keywords>" --limit 12 --format markdown
python3 <skill-dir>/scripts/index_codebase.py --root <repo> --format stats --limit 20
```

Treat index results as candidate reads. Prefer compiler/LSP/SCIP evidence, then structural indexes,
then `rg`. Fall back to `rg` and direct reads when Python is unavailable or a query returns no useful
candidates. Regenerate after structural changes and commit an index only when the repository declares
it authoritative.

Complete this phase when current entrypoints, owners, dependency direction, commands, verification
surfaces, stale generations, and unknowns are accounted for.

For a mapping, readiness audit, or other read-only request, stop mutation here and continue directly
to the evidence handoff in phase 5. Phases 3–4 require explicit authority to change the checkout.

## 3. Select only the required branches

- **New or extended code:** read [reuse-placement.md](references/reuse-placement.md). Apply
  `Search → Reuse → Extend → Localize → Extract`; record material decisions as
  `Intent / Search / Decision / Owner / Why`.
- **Conventions or budgets:** read [code-conventions.md](references/code-conventions.md). Baseline
  before setting thresholds and give every rule a scope, check, rationale, exception policy, and
  owner.
- **Cleanup or restructuring:** read [cleanup-refactor.md](references/cleanup-refactor.md). Classify
  every questioned resource as `keep`, `migrate`, `archive`, `delete`, or `unknown`; migrate
  consumers before removal.
- **Durable documentation:** read [docs-system.md](references/docs-system.md). Extend the repository's
  existing documentation owners and trust order. Read
  [agent-entrypoints.md](references/agent-entrypoints.md) only when creating or synchronizing coding-
  agent entrypoints.
- **Tooling and operations:** read [stack-patterns.md](references/stack-patterns.md). Add only
  capabilities justified by the selected stack and objective.

Complete branch selection when every proposed change belongs to one selected branch and every
unselected branch is outside the accepted scope.

## 4. Implement in dependency order

1. Stabilize runtime pins, package management, source roots, and shared contracts.
2. Characterize behavior at seams that will move.
3. Migrate consumers one bounded owner at a time.
4. Add truthful configuration, local services, commands, tests, and enforcement.
5. Update durable documentation after the implementation is stable.
6. Add or repair CI only after the same local gates work.
7. Regenerate the final index and any repository-owned agent entrypoints.

Keep secrets out of committed files and client bundles. Inspect generated output before accepting it.

Complete implementation when each accepted outcome has one owner, its consumers use the new path,
and superseded resources have passed the cleanup gate.

## 5. Verify and hand off

Run narrow checks first, then every supported full gate applicable to the change. Report unavailable
infrastructure as unrun. Require evidence that:

- install, build, static checks, tests, startup, migrations, and deployment paths touched by the work
  remain truthful;
- moved or removed resources have no unintended consumers;
- boundaries, conventions, reuse decisions, and documentation match the final checkout;
- internal links resolve and only intended working-tree changes remain.

Finish with changed owners and boundaries, exact commands and results, unrun checks, calibrated
readiness claims, and remaining debt. Bootstrap is complete only when every accepted outcome maps to
current checkout evidence or an explicitly named limitation.
