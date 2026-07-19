# Reuse and placement gate

Force a checkout-derived decision before creating or widening source symbols. Optimize for the smallest coherent change, not the fewest keystrokes.

## Contents

- [Named principles](#named-principles)
- [Mandatory decision](#mandatory-decision)
- [Search protocol](#search-protocol)
- [Decision ladder](#decision-ladder)
- [Placement lattice](#placement-lattice)
- [Functions and methods](#functions-and-methods)
- [Components and hooks](#components-and-hooks)
- [Classes, services, schemas, and types](#classes-services-schemas-and-types)
- [Simplicity and optimization](#simplicity-and-optimization)
- [Verification](#verification)

## Named principles

| Keyword | Operational rule |
| --- | --- |
| **KISS** | Choose the least complex design that satisfies observed requirements. |
| **YAGNI** | Add no variation point, option, layer, dependency, or public API for hypothetical use. |
| **AHA** | Avoid hasty abstractions; prefer temporary local duplication over the wrong shared concept. |
| **Rule of Three** | Treat repetition as evidence to inspect, not an automatic extraction trigger. |
| **DRY** | Give each invariant or item of knowledge one authoritative owner. |
| **Common Closure Principle** | Place code that changes for the same reason together. |
| **Common Reuse Principle** | Group only code that consumers actually reuse together. |
| **Information Hiding** | Hide volatile decisions; expose the smallest stable contract. |
| **Locality of Behavior** | Keep behavior near the state, UI, route, or domain rule it explains. |

## Mandatory decision

Before writing a non-trivial function, method, component, hook, class, service, schema, type, or module:

```text
Intent: behavior, invariant, inputs, outputs, side effects
Search: semantic queries, symbols, imports, exports, tests, candidates
Decision: reuse | extend | local | extract | replace
Owner: narrowest file/module allowed by dependency direction
Why: contract fit, cohesion, consumers, complexity, performance evidence
```

Keep this in the task plan or working notes; do not create a permanent decision file for routine code. Skip narration only for mechanically obvious edits such as renames or direct generated output.

## Search protocol

Search by behavior and domain language before searching by the proposed identifier:

```bash
python3 <skill-dir>/scripts/index_codebase.py --root <repo> --query "<domain behavior input output>" --limit 15 --format markdown
rg -n "<existing term|synonym|UI label|error text|schema field>" <source-roots>
```

Then:

1. Query LSP/SCIP workspace symbols and definitions when available.
2. Inspect public exports, dependency injection registries, route/tool registration, component catalogs, schemas, and package manifests.
3. Read candidate implementations, call sites, nearest tests, and boundary configuration.
4. Compare semantics: accepted inputs, normalization, errors, side effects, security, accessibility, performance, and ownership.
5. Search again after learning the repository's canonical vocabulary.

Name similarity is weak evidence. A differently named symbol may own the same behavior; an identically named symbol in another bounded context may not be reusable.

## Decision ladder

Choose the first valid outcome:

1. **Reuse:** call or compose an existing symbol when its full contract matches.
2. **Extend:** modify the existing owner when the new case shares its invariant, abstraction level, and change reason; preserve existing consumers.
3. **Local:** keep one-use behavior inline, private, or feature-local when sharing is unproven.
4. **Extract:** create an abstraction only when current call sites express one stable concept and can depend on the same owner.
5. **Replace:** introduce a simpler owner, migrate every consumer, then remove the superseded path after verification.

Reject reuse when it requires misleading names, flag-driven unrelated behavior, dependency inversion, leaky domain knowledge, or weakened contracts. Reject extraction when only syntax is duplicated.

## Placement lattice

Place code at the narrowest level that owns its invariant:

1. expression or local closure;
2. private function/method in the owning file;
3. dedicated file inside the feature or bounded context;
4. feature-internal module used by several files in that feature;
5. domain contract/core module used by several features;
6. workspace package or design-system primitive used by independent owners;
7. external standard/library when it is smaller, maintained, and already compatible.

Promotion requires evidence. Never move a helper to `shared`, `common`, `utils`, or a design system merely because a second caller exists. The destination must own the name, invariant, dependency direction, and change cadence.

## Functions and methods

- Reuse canonical parsing, normalization, validation, authorization, mapping, date/time, identifier, and domain-calculation functions.
- Prefer a pure function for deterministic transformations; isolate I/O, time, randomness, and global state at edges.
- Keep a one-caller helper private unless its contract is independently meaningful or directly test-worthy.
- Generalize from actual call sites. Prefer explicit parameters over option objects until options form one coherent configuration concept.
- Avoid boolean flags that select unrelated algorithms; separate behavior or inject a demonstrated strategy.
- Do not create a wrapper that only renames a call. Require policy, adaptation, boundary protection, instrumentation, or a stable seam.
- Extend an existing function only when its name remains truthful and its complexity does not become a dispatcher for unrelated cases.

## Components and hooks

- Search the platform toolkit, design system, feature components, route layouts, story catalog, and accessibility primitives first.
- Reuse a component only when semantic role, interaction, accessibility, state ownership, and visual contract match.
- Compose primitives before adding variant props. Reject mutually exclusive prop sets and conditional “god components.”
- Keep page- or feature-specific composition beside that page/feature; extract a feature component when it has a stable UI responsibility.
- Promote a component to the design system only when independent features share its semantics, not merely its current styling.
- Use a wrapper when it binds domain policy or adapts a stable external primitive; do not fork the primitive for cosmetic convenience.
- Extract a hook for reusable stateful behavior or lifecycle coordination. Keep simple derivation as a function and local state local.
- Search existing loading, empty, error, permission, responsive, analytics, and form patterns before creating another state treatment.

## Classes, services, schemas, and types

- Reuse or extend the authoritative schema/type; do not mirror a contract unless a documented boundary requires decoupling.
- Introduce a class or service for lifecycle, stateful invariants, framework integration, substitution, or owned orchestration—not as a namespace for functions.
- Do not create one interface per implementation. Add an abstraction at a volatile boundary or when multiple real implementations require substitution.
- Keep transport DTOs, persistence shapes, domain models, and view models distinct only when their contracts genuinely differ.
- Prefer the existing registry/provider mechanism over a parallel factory or service locator.
- Add a new module/package only when it creates a real ownership boundary and preserves acyclic dependency direction.

## Simplicity and optimization

Use this priority:

`correctness → contract reuse → conceptual simplicity → measured performance → speculative flexibility`

- Minimize new symbols, public APIs, layers, dependencies, configuration, branches, and concepts introduced by the change.
- Prefer standard language/runtime/library facilities already used by the repository.
- Choose an asymptotically appropriate data structure and avoid obvious repeated I/O, N+1 access, unnecessary serialization, or duplicate work.
- Measure hot paths before micro-optimizing. Support performance claims with a representative benchmark, profile, workload bound, or complexity argument.
- Optimize for change when runtime evidence is absent: clear control flow and a narrow contract are usually cheaper than a clever generic engine.
- Delete dead branches, unused options, redundant wrappers, and superseded helpers within the authorized change scope.
- Treat fewer lines as useful only when meaning remains explicit; compressed or magical code is not simpler.

## Verification

Before finishing:

1. Repeat the semantic search and confirm no suitable owner was missed.
2. Inspect all consumers of any extended, extracted, moved, or replaced symbol.
3. Run the nearest tests plus type, lint, architecture, and performance checks justified by the change.
4. Confirm public exports and dependency direction remain deliberate.
5. Confirm no old implementation, parallel registry, duplicated contract, or dead option remains.
6. Report the reuse/placement decision for material additions and any unresolved candidate.
