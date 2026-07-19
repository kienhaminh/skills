---
name: bootstrap
description: Set up, map, clean, or rehabilitate a software repository around a user-selected technology stack using named software-engineering methods, mandatory reuse and placement decisions, enforceable code conventions, per-file source indexing, precise code navigation, safe legacy-resource removal, incremental restructuring, agent-oriented documentation, honest command surfaces, testing, debugging, security, and exploration affordances. Use when starting a codebase, understanding or standardizing an inherited repository, forcing agents to prefer simple existing code over speculative functions, components, classes, hooks, or abstractions, defining naming, module, complexity, duplication, or OOP rules, removing obsolete code or tooling, reorganizing modules or packages, choosing repo structure and developer tooling, creating a professional docs system, or making a project token-efficient for coding agents.
---

# Bootstrap a codebase

Build a repository another agent can understand, run, test, and change without reconstructing hidden context.

## Establish the contract

Extract the product shape, chosen stack, deployment target, constraints, and required quality gates from the request. Infer them from an existing checkout when possible. Ask only when a missing choice would materially change architecture or create an irreversible dependency.

Separate three states:

- **Observed** — proven by files or commands.
- **Requested** — explicitly chosen by the user.
- **Proposed** — a recommendation awaiting implementation.

Never document proposed behavior as implemented.

## Apply named methods

Use the shortest applicable chain; read [scientific-methods.md](references/scientific-methods.md) for operational definitions and sources.

`GQM → Software Reflexion Model → Information Hiding/Bounded Context → C4/arc42 → ADR → Diátaxis → Information Foraging → Repository Map → LSP/SCIP`

- Use **GQM** to turn quality goals into questions and measurable gates.
- Use a **Software Reflexion Model** to compare the intended architecture with dependencies recovered from source.
- Use **Information Hiding**, **Bounded Contexts**, and **Stable Dependencies** to define source boundaries.
- Use **C4** and the **arc42 Building Block View** to zoom from system to source boundaries without mixing abstraction levels.
- Use **ADRs** for architecturally significant decisions and supersession history.
- Use **Diátaxis** to separate tutorial, how-to, reference, and explanation.
- Use **Information Scent**, a **Repository Map**, and **Precise Code Navigation** to minimize the read set.

## Inspect before designing

Preserve unrelated work. Read repository instructions and status first, then inspect manifests, locks, version pins, source roots, configs, CI, tests, env examples, containers, migrations, and existing docs.

Run:

```bash
python3 <skill-dir>/scripts/inspect_codebase.py --root <repo> --format markdown
```

Use `rg --files` and targeted reads to verify anything the report cannot classify. Treat live code and executable configuration as stronger evidence than prose. Identify stale generations rather than merging them into the current design.

## Build a checkout-derived code map

Read [code-navigation.md](references/code-navigation.md). Generate evidence from the current tree instead of relying on memory or hand-written per-file summaries.

```bash
python3 <skill-dir>/scripts/index_codebase.py --root <repo> --format ndjson
python3 <skill-dir>/scripts/index_codebase.py --root <repo> --query "<task keywords>" --limit 12 --format markdown
python3 <skill-dir>/scripts/index_codebase.py --root <repo> --format stats --limit 20
```

Index every supported source file by path, language, role, size, hash, leading keywords, top-level symbols, imports, and symbol line numbers. Use the query result only as a candidate read set:

1. Read the owning entrypoint or public contract.
2. Follow definitions and references with LSP/SCIP when available.
3. Read the implementation slice, its nearest tests, and owning configuration.
4. Expand only when imports, runtime registration, or failing evidence crosses the boundary.

Prefer compiler/LSP/SCIP evidence over regex tags; prefer structural Tree-sitter/ctags tags over plain text search; use `rg` as the universal fallback. Regenerate the map after structural changes. Do not commit generated indexes unless the repository explicitly owns them.

## Gate every new symbol

Read [reuse-placement.md](references/reuse-placement.md) before adding or materially extending a function, method, component, hook, class, service, schema, type, or module.

Apply `Search → Reuse → Extend → Localize → Extract`:

1. Define the behavior, invariant, inputs, outputs, and side effects—not the proposed name.
2. Search the live index, LSP symbols/references, exports, tests, registries, and lexical synonyms for an existing semantic owner.
3. Reuse an exact contract; extend only when responsibility and change cadence remain cohesive.
4. Otherwise keep the implementation at the narrowest valid scope. Promote it only when current evidence proves a shared concept.
5. Reject speculative options, generic wrappers, pass-through layers, and abstractions without real consumers.

Use **KISS**, **YAGNI**, **AHA**, **Rule of Three**, **Common Closure Principle**, and **Common Reuse Principle**. Prefer composition over configurable conditionals. Optimize measured hot paths and material complexity; do not trade readability for hypothetical performance.

For every non-trivial new symbol, retain a compact decision in the working notes or plan:

```text
Intent: <behavior and invariant>
Search: <queries and candidates inspected>
Decision: reuse | extend | local | extract | replace
Owner: <narrowest responsible file/module>
Why: <contract, cohesion, dependency, and complexity evidence>
```

## Design enforceable conventions

Read [code-conventions.md](references/code-conventions.md) before creating or rewriting `CONVENTIONS.md`, source roots, naming rules, or module budgets.

Use **Information Hiding**, **High Cohesion / Low Coupling**, **DRY**, **AHA**, **Rule of Three**, **SOLID**, **Law of Demeter**, **Cyclomatic Complexity**, **Cognitive Complexity**, and **CK Metrics** as decision vocabulary. Apply OOP rules only to object-oriented boundaries; do not manufacture classes or interfaces around simple data transformations.

Baseline the current tree before setting thresholds. LOC is a screening signal, not a split algorithm: calibrate budgets from the repository distribution, mark generated/declarative exceptions, then ratchet toward the target. Split by responsibility, change reason, domain boundary, or dependency direction—not at an arbitrary line number.

Every convention must specify:

- scope and stack-native naming;
- a checkable rule and its rationale;
- warning and failure thresholds where relevant;
- explicit exceptions and their owner;
- the formatter, linter, architecture test, clone detector, or CI command that enforces it.

Prefer feature or bounded-context ownership with layers inside the boundary. Keep one authoritative representation of each contract, schema, configuration fact, and domain rule. Avoid generic dumping grounds such as `utils`, `common`, or `helpers` unless their domain and dependency direction are explicit.

## Clean and reshape deliberately

Read [cleanup-refactor.md](references/cleanup-refactor.md) before deleting resources, moving source roots, splitting packages, or replacing a legacy generation.

Inventory code, docs, assets, scripts, dependencies, generated artifacts, infrastructure, CI, deployment, migrations, and data paths. Classify each questioned resource as **keep**, **migrate**, **archive**, **delete**, or **unknown**, with evidence. A filename or zero `rg` hits is a signal, never proof.

Protect behavior before structural change:

1. Capture entrypoints, public contracts, runtime paths, and current gates.
2. Add characterization coverage where behavior is not already pinned.
3. Define the target tree and dependency direction.
4. Move one boundary at a time; update imports, configs, tests, and docs together.
5. Remove adapters and old resources only after all consumers migrate.

Prefer reversible moves and reviewable deletion sets. Never delete ambiguous data, migrations, secrets, user assets, compatibility surfaces, or deployment resources without proving ownership and replacement. Do not combine broad cleanup with unrelated feature work.

## Design the source of truth

Keep the current code layout unless the user asked to restructure it. Prefer a compact documentation router over a large handbook. Apply the detailed pattern in [docs-system.md](references/docs-system.md).

At minimum, establish:

1. A root runbook for prerequisites, setup, run, and core commands.
2. A root agent entrypoint that routes readers to authoritative files.
3. A docs index that states trust order and marks current versus historical material.
4. Architecture, code conventions, security, testing, debugging, and planning ownership.
5. Active, completed, and debt locations for work state.

Link; do not duplicate. Put product behavior, architecture, operational procedure, and temporary plans in different owners.

## Complete the agent surface

Select only the capabilities justified by the chosen stack and project scope. Read [stack-patterns.md](references/stack-patterns.md) when choosing tooling.

Make these operations discoverable and truthful:

- Pin runtime and package-manager versions.
- Provide one canonical install, dev, build, type-check, lint, format, unit-test, integration-test, and end-to-end command where applicable.
- Keep env examples beside their owning app; validate required config at startup.
- Provide deterministic fakes, fixtures, seeds, and offline modes for external or AI services.
- Make local dependencies reproducible with the smallest suitable mechanism.
- Expose cheap health and structured logs before proposing a monitoring stack.
- Preserve schemas, migrations, API contracts, generated-client commands, and data-inspection routes.
- Separate fast default tests from infrastructure-dependent suites.
- Encode the same gates in CI; never advertise a command that silently does nothing.

Do not add a dependency merely because it appears in the reference. Match complexity to the repository's real risk and operating scale.

## Implement in dependency order

1. Baseline behavior, commands, and working-tree state.
2. Define GQM goals, questions, metrics, and stop conditions.
3. Generate the file index and actual dependency view.
4. Baseline size, complexity, coupling, cycles, and duplication; design the convention profile.
5. Compare intended and actual boundaries with a Software Reflexion Model.
6. Classify legacy resources and approve the target tree.
7. Pin runtimes and package management.
8. Establish source roots and shared boundaries.
9. Migrate consumers, then remove superseded resources.
10. Apply the reuse-and-placement gate before adding source symbols; record owned exceptions.
11. Add config, local dependency setup, commands, test layers, and convention enforcement.
12. Write C4/arc42 views, ADRs, and Diátaxis-routed docs from verified behavior.
13. Add CI gates after local commands work.
14. Regenerate indexes and repair broken references and links.

Use existing generators only when their output matches the chosen architecture. Inspect generated changes before accepting them. Keep secrets out of committed files and browser bundles.

## Verify the setup

Run the narrowest checks first, then the whole supported gate. Report unavailable infrastructure as unrun, not green.

Require evidence for:

- clean install from the declared lockfile;
- build or compile;
- type-check and lint/format checks;
- fast tests without optional infrastructure;
- integration and end-to-end tests when their dependencies are available;
- startup plus health/readiness behavior;
- migration and seed paths, when present;
- no remaining consumers of deleted or moved resources;
- dependency, workspace, path-alias, CI, and deployment references updated after restructuring;
- regenerated source index matches the final tree and exposes every supported source file;
- intended-versus-actual architecture differences are resolved or recorded as debt;
- naming, dependency-direction, complexity, file-budget, and duplication checks match the documented convention profile;
- large or complex files are split by coherent responsibility, or carry a named, owned exception;
- no duplicated source of truth exists for contracts, schemas, configuration facts, or domain rules;
- each non-trivial new symbol has a reuse/placement decision grounded in inspected candidates;
- shared abstractions have real consumers with one invariant and compatible change cadence;
- no redundant wrapper, speculative option, pass-through layer, or custom implementation duplicates a suitable existing contract;
- performance or efficiency claims are supported by workload evidence, profiling, a benchmark, or an explicit complexity argument;
- internal documentation links;
- clean working-tree scope containing only intended changes.

Finish with: what was created, chosen boundaries, exact commands run, checks not run and why, and remaining debt. Do not claim “production-ready” without deployment, recovery, security, and operational evidence.
