---
name: bootstrap
description: Set up, map, clean, or rehabilitate a software repository using live evidence, reuse-first design, enforceable conventions, safe restructuring, code indexing, truthful commands, and synchronized AGENTS.md and CLAUDE.md entrypoints. Use for new or inherited codebases, repository cleanup or reorganization, architecture and documentation standardization, or making a project efficient for coding agents.
---

# Bootstrap a codebase

Build a repository another agent can understand, run, test, and change without reconstructing hidden
context.

## Establish the contract

Read repository instructions and status first. Infer product shape, stack, deployment target,
constraints, and quality gates from the request and checkout. Ask only when a missing choice would
materially change architecture or create an irreversible dependency.

Keep these states separate:

- **Observed** - proven by files or commands.
- **Requested** - explicitly chosen by the user.
- **Proposed** - recommended but not implemented.

Never document proposed behaviour as current.

Use the shortest applicable method chain from
[scientific-methods.md](references/scientific-methods.md):

`GQM -> Software Reflexion Model -> Information Hiding/Bounded Context -> C4/arc42 -> ADR -> Diataxis -> Information Foraging -> Repository Map -> LSP/SCIP`

## Inspect and map the checkout

Preserve unrelated work. Inspect manifests, locks, version pins, source roots, configs, CI, tests,
environment examples, containers, migrations, and docs.

```bash
python3 <skill-dir>/scripts/inspect_codebase.py --root <repo> --format markdown
```

Use `rg --files` and targeted reads to verify anything the report cannot classify. Treat live code
and executable configuration as stronger evidence than prose; identify stale generations instead of
merging them into the current design.

Read [code-navigation.md](references/code-navigation.md), then generate a checkout-derived index:

```bash
python3 <skill-dir>/scripts/index_codebase.py --root <repo> --format ndjson
python3 <skill-dir>/scripts/index_codebase.py --root <repo> --query "<task keywords>" --limit 12 --format markdown
python3 <skill-dir>/scripts/index_codebase.py --root <repo> --format stats --limit 20
```

Use query results only as candidate reads. Follow the owning contract, definitions and references,
implementation, nearest tests, and configuration. Prefer compiler/LSP/SCIP evidence, then structural
tags, then `rg`. Regenerate after structural changes; do not commit indexes unless the repository
owns them.

## Reuse and place deliberately

Read [reuse-placement.md](references/reuse-placement.md) before adding or materially extending a
function, component, hook, class, service, schema, type, or module.

Apply `Search -> Reuse -> Extend -> Localize -> Extract`:

1. define behaviour, invariant, inputs, outputs, and side effects;
2. search symbols, references, exports, tests, registries, and synonyms for an owner;
3. reuse an exact contract or extend a cohesive owner;
4. otherwise keep the implementation at the narrowest valid scope;
5. extract only when current consumers prove a shared concept.

Record non-trivial decisions as `Intent / Search / Decision / Owner / Why`. Reject speculative
options, pass-through layers, and abstractions without real consumers.

## Make conventions enforceable

Read [code-conventions.md](references/code-conventions.md) before changing `CONVENTIONS.md`, naming,
source boundaries, or budgets.

Baseline the repository before setting thresholds. Split by responsibility, change reason, domain
boundary, or dependency direction - never by line count alone. Every convention must name its scope,
checkable rule, rationale, thresholds, exceptions, owner, and enforcement command. Keep one owner for
each contract, schema, configuration fact, and domain rule.

## Clean and reshape safely

Read [cleanup-refactor.md](references/cleanup-refactor.md) before deleting, moving, splitting, or
replacing resources.

Classify questioned code, docs, assets, dependencies, generated files, infrastructure, migrations,
and data paths as **keep**, **migrate**, **archive**, **delete**, or **unknown**, with evidence. A name
or zero search hits is never proof of safety.

Before structural change:

1. capture entrypoints, public contracts, runtime paths, and current gates;
2. add characterization coverage where behaviour is unpinned;
3. define the target tree and dependency direction;
4. migrate one boundary and all consumers at a time;
5. remove old resources only after replacement is proven.

Never delete ambiguous data, migrations, secrets, user assets, compatibility surfaces, or deployment
resources. Keep cleanup separate from unrelated feature work.

## Build the source of truth

Read [docs-system.md](references/docs-system.md) and
[agent-entrypoints.md](references/agent-entrypoints.md) before changing durable docs, `AGENTS.md`, or
`CLAUDE.md`.

Establish only justified owners:

1. root setup and command runbook;
2. docs index with trust order and current-versus-historical routing;
3. architecture, conventions, security, testing, debugging, and planning docs;
4. active, completed, and debt locations;
5. root `AGENTS.md` and `CLAUDE.md` routing to the same authoritative tree.

Read existing entrypoints for binding rules at the start, but write their shared map last. Preserve
non-conflicting rules, normalize equivalents, retain stricter compatible details, and surface
conflicts. Copy the canonical core block from `agent-entrypoints.md` byte-for-byte, render the source
tree from the final checkout, and keep shared sections identical unless an explicit tool-specific
delta is necessary. Link; do not duplicate.

## Expose truthful operations

Read [stack-patterns.md](references/stack-patterns.md) when choosing tooling. Add only capabilities
the stack and scope justify:

- pinned runtime and package-manager versions;
- canonical install, dev, build, type-check, lint, format, and test commands;
- validated configuration and non-secret environment examples;
- deterministic fakes, fixtures, seeds, and offline modes where needed;
- reproducible local dependencies, migrations, schemas, and generated-client paths;
- cheap health and structured logs before a monitoring stack;
- fast default tests separated from infrastructure-dependent suites;
- CI gates that run the same meaningful local commands.

Do not advertise no-op commands or add dependencies merely because a reference mentions them.

## Implement in dependency order

1. Baseline behaviour, commands, working tree, and GQM stop conditions.
2. Generate the source/dependency map and baseline boundaries, complexity, cycles, and duplication.
3. Classify legacy resources and approve the target tree.
4. Pin runtimes, package management, source roots, and shared contracts.
5. Migrate consumers before removing superseded resources.
6. Apply reuse/placement decisions to new symbols.
7. Add configuration, local services, commands, tests, and convention enforcement.
8. Write verified architecture, ADR, and Diataxis-routed docs.
9. Add CI only after local gates work.
10. Repair the supported gates, regenerate the final index, then finalize both agent entrypoints.

Inspect generator output before accepting it. Keep secrets out of committed files and browser
bundles.

## Verify

Run narrow checks first, then the supported full gate. Report unavailable infrastructure as unrun.
Require evidence that:

- install, build, type-check, formatting/linting, and supported test layers are truthful;
- startup, health, migration, seed, CI, workspace, and deployment paths still resolve;
- moved or deleted resources have no remaining consumers;
- the final source index and intended architecture match the checkout or record named debt;
- conventions, boundaries, duplication, complexity, and reuse decisions are enforced;
- internal documentation links resolve and only intended working-tree changes remain;
- `AGENTS.md` and `CLAUDE.md` contain the current source tree and exact canonical core block, preserve
  compatible prior rules, and either share the same operating map or document tested deltas.

Finish with created or changed owners, chosen boundaries, exact commands and results, unrun checks,
and remaining debt. Do not claim production readiness without deployment, recovery, security, and
operational evidence.
