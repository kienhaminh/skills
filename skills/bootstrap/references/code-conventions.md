# Code convention design

Conventions are executable architecture. Derive them from the stack, domain, and measured checkout; do not paste a universal style sheet.

## Contents

- [Leading keywords](#leading-keywords)
- [Convention design loop](#convention-design-loop)
- [Required convention profile](#required-convention-profile)
- [Naming](#naming)
- [Source tree and module boundaries](#source-tree-and-module-boundaries)
- [Size and complexity budgets](#size-and-complexity-budgets)
- [Duplication and canonical knowledge](#duplication-and-canonical-knowledge)
- [OOP and paradigm rules](#oop-and-paradigm-rules)
- [Enforcement matrix](#enforcement-matrix)
- [Agent readability gate](#agent-readability-gate)

## Leading keywords

| Keyword | Decision it leads |
| --- | --- |
| **Information Hiding** | Hide volatile design decisions behind a stable module boundary. |
| **Bounded Context** | Give each domain model and vocabulary one explicit owner. |
| **High Cohesion / Low Coupling** | Group code that changes together; minimize cross-boundary knowledge. |
| **Stable Dependencies Principle** | Direct dependencies toward the more stable contract or policy. |
| **Acyclic Dependencies Principle** | Reject package/module dependency cycles. |
| **DRY** | Keep each item of knowledge in one authoritative representation. |
| **KISS / YAGNI** | Prefer the smallest observed solution; reject speculative variation points. |
| **AHA** | Delay abstraction until real call sites reveal a stable contract. |
| **Rule of Three** | Tolerate incidental similarity until a stable shared concept is proven. |
| **Common Closure / Common Reuse** | Place code by shared change reason and actual reuse set. |
| **SOLID** | Review object-oriented extension points and contracts. Do not use it as a class-count target. |
| **Law of Demeter** | Keep collaborators local; avoid navigation through object graphs. |
| **Composition over Inheritance** | Reuse behavior without creating fragile subtype hierarchies. |
| **Cyclomatic Complexity** | Flag branch-heavy behavior and test-path growth. |
| **Cognitive Complexity** | Flag control flow that is hard for a reader to retain. |
| **CK Metrics** | Review class-level complexity, coupling, response surface, cohesion, and inheritance. |
| **Ratcheting** | Prevent new violations first, then lower the baseline deliberately. |

## Convention design loop

1. **Adopt native style:** use the language/framework formatter and canonical style guide before inventing local syntax rules.
2. **Measure baseline:** record physical LOC distribution, largest files, dependency cycles, complexity, coupling, and duplicate blocks.
3. **Define profile:** write rules, rationale, scope, warning/failure thresholds, exceptions, and enforcement command.
4. **Rehabilitate safely:** gate changed/new code first; reduce legacy violations in bounded batches.
5. **Enforce locally:** make every check independently runnable and fast enough for its intended loop.
6. **Mirror in CI:** run the same commands; do not maintain a second CI-only policy.
7. **Ratchet:** update thresholds only from reviewed evidence. Never relax a gate silently.

Start with:

```bash
python3 <skill-dir>/scripts/index_codebase.py --root <repo> --format stats --limit 20
```

This reports physical lines, not logical statements. Add the stack's native analyzer before enforcing complexity or clone thresholds.

## Required convention profile

Put the authoritative profile in the repository's discovered convention owner. If none exists and
the user authorizes a new owner, choose its path from the repository's documentation structure. Keep
agent entrypoints as routers, not duplicate rulebooks.

```markdown
# Code conventions

## Scope and authority
## Naming
## Source tree and dependency direction
## Reuse and placement gate
## File and function budgets
## Duplication and canonical knowledge
## Paradigm rules: OOP, functional, data-oriented
## Error, boundary, and configuration rules
## Tests and source pairing
## Generated code and exceptions
## Enforcement commands
## Ratchet baseline and target
```

For every normative rule use this compact contract:

```text
Rule: <observable requirement>
Why: <quality goal or protected boundary>
Scope: <languages, roots, or roles>
Check: <exact local command>
Warn/Fail: <thresholds, if any>
Exceptions: <allowed cases, owner, expiry/review condition>
```

## Naming

- Use domain vocabulary and one term per concept. Add a glossary when two bounded contexts legitimately use different meanings.
- Follow stack-native casing for packages, files, types, functions, variables, constants, and tests. Formatters do not settle semantic naming.
- Make the filename reveal its primary responsibility or public symbol. Follow framework-reserved names exactly.
- Name types and data as nouns; name actions as verbs; name booleans as predicates. Avoid type noise already expressed by the language.
- Scale descriptiveness with scope. Short conventional names are acceptable only in a small, obvious scope.
- Keep source/test pairing mechanically discoverable using the ecosystem's conventional suffix and location.
- Avoid vague roots and files: `utils`, `helpers`, `common`, `misc`, `base`, `manager`, `processor`, `service`. If one is necessary, qualify it by domain and state the allowed contents.
- Do not encode temporary generations such as `new`, `old`, `v2`, or `final` in names unless versioning is part of a public protocol. Migrate, supersede, and remove instead.

## Source tree and module boundaries

- Prefer **package by feature / bounded context**. Place delivery, application, domain, and infrastructure layers inside a feature only when the system actually needs those layers.
- Give every source file one primary responsibility and every directory one explicit owner. Private supporting declarations may remain with the owning behavior.
- Keep entrypoints thin: assemble dependencies and start the runtime; move policy into owned modules.
- Expose a deliberate public API per module. Import through that API across boundaries; use direct internal imports only within the owner.
- Direct dependencies inward toward domain policy or stable contracts. Keep transport, persistence, framework, and vendor details at the edges.
- Reject dependency cycles. Treat a new `shared` package as an architectural decision, not a convenient escape hatch.
- Split a directory when it contains multiple vocabularies or independent change reasons. Merge directories that only relay names without hiding a decision.
- Avoid excessive nesting. Each path segment must add ownership, domain, platform, or lifecycle information.
- Keep schemas, migrations, generated outputs, fixtures, and assets in explicit roots so agents can include or exclude them reliably.

## Size and complexity budgets

There is no universal scientific maximum LOC. Use file size as an attention budget and complexity/coupling as stronger evidence.

For a greenfield repository without a stronger stack convention, start with these **operational defaults**, then tune with GQM evidence:

| Signal | Warn | Review/fail policy |
| --- | ---: | --- |
| Hand-written source file | >300 physical lines | >500 requires split or a named exception |
| Function/method | >50 physical lines | review responsibility and control flow |
| Cyclomatic complexity | >10 per callable | split or justify branch-heavy algorithm |
| Cognitive complexity | use analyzer default | do not raise the default without evidence |
| Directory breadth | >30 direct source files | review missing feature/module boundary |

For an inherited repository:

1. Measure median, p90, p95, and maximum per language and role.
2. Exclude generated code, vendored code, lockfiles, migrations, snapshots, fixtures, and large declarative schemas from the handwritten-code gate.
3. Set the first gate to prevent new or worsened violations; record existing violations as a baseline.
4. Prioritize files that combine high size with high complexity, coupling, churn, or defect evidence.
5. Ratchet toward the target in reviewable batches.

Never split solely to satisfy LOC. Split at a stable seam: separate responsibilities, domain policies, adapters, commands/queries, parsing/validation, or independent test surfaces. A large cohesive lookup table may be safer than fragmented indirection.

## Duplication and canonical knowledge

- Apply the mandatory reuse-and-placement gate in `reuse-placement.md` before creating or promoting source symbols.
- Apply **DRY** to knowledge, not merely identical text. Contracts, schemas, validation rules, feature flags, environment facts, and domain formulas need one authoritative owner.
- Use a clone detector for exact and near-duplicate blocks; use search and the source index to find duplicated symbols and concepts.
- Apply the **Rule of Three** before extracting incidental implementation similarity. Two similar blocks in separate bounded contexts may be intentional.
- Extract only when the shared abstraction has one name, one invariant, and compatible change cadence.
- Prefer generation from a canonical schema over copying representations. Keep the generator and drift check beside the owner.
- Do not create a universal helper layer that couples unrelated features. Local duplication can be cheaper than the wrong dependency.
- Document deliberate duplication with the boundary it protects and the condition that would trigger consolidation.

## OOP and paradigm rules

Apply **SOLID** where objects model durable behavior or substitution:

- **SRP:** one actor or reason to change per module/class; not one method per class.
- **OCP:** introduce extension points only where variation is demonstrated and stable.
- **LSP:** prove substitutability with shared contract tests, including failure semantics.
- **ISP:** expose consumer-specific capabilities; avoid broad interfaces and speculative methods.
- **DIP:** depend on abstractions at volatile I/O, vendor, clock, randomness, and policy boundaries. Do not create one interface per concrete class.
- Apply **Law of Demeter** to avoid train-wreck access and leaked object graphs.
- Prefer composition over inheritance; keep inheritance shallow and semantic.
- Keep behavior with the state/invariant it protects. Avoid anemic objects when the domain is behavior-rich.

Do not force OOP into pure transformations, parsers, numerical code, or immutable data pipelines. For those, prefer small pure functions, explicit data flow, immutable values, and side effects isolated at boundaries.

Use CK metrics as review prompts, not score targets:

- **WMC:** class behavior/complexity load;
- **CBO:** coupling to other classes/modules;
- **RFC:** reachable response surface;
- **LCOM:** lack of cohesion suggesting multiple responsibilities;
- **DIT/NOC:** inheritance depth and breadth.

## Enforcement matrix

Select existing native tools first; add only what answers a GQM question.

| Concern | Preferred enforcement |
| --- | --- |
| New symbol reuse/placement | review checklist + indexed semantic search + architecture tests |
| Syntax/casing/import order | formatter + language linter |
| File/function budgets | linter rule or small repository check |
| Cyclomatic/cognitive complexity | language analyzer or Sonar-compatible rule |
| Dependency direction/cycles | architecture test, import-boundary linter, or dependency graph check |
| Exact/near clones | clone detector with generated/test exclusions |
| Public contracts | type-checker + contract tests + schema drift check |
| Source/test pairing | test discovery check or repository script |
| Exceptions | narrow suppression with reason, owner, and review/expiry condition |

Keep formatter, linter, type-check, architecture, duplication, and test commands separate even if an aggregate `check` command invokes all of them. Agents need the narrowest failing signal.

## Agent readability gate

Before accepting the convention profile, verify that an unfamiliar agent can:

1. infer a file's owner and role from its path and name;
2. locate the public contract, implementation, tests, and configuration from one index query;
3. identify allowed dependency direction without reading the entire repository;
4. distinguish generated, historical, and active source;
5. run one narrow command for each rule category;
6. find every exception and its rationale without relying on chat memory.

If the answer depends on tribal knowledge, encode the missing scent in names, a local README, the docs router, an architecture test, or the convention owner.
