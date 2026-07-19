# Documentation system

Use this as a pattern, not a mandatory filename inventory. Extend an existing coherent system instead of replacing it.

## Trust and routing

Declare a short trust order near the docs entrypoint:

1. Runtime behavior and executable code.
2. Approved architecture decisions and binding rule files.
3. Descriptive docs and plans.
4. Historical material.

Mark outdated generations explicitly. Never let a historical doc silently compete with current architecture.

## Diátaxis lens

Classify each document before placing it:

- **Tutorial** — guided learning with a successful end state.
- **How-to** — task-oriented procedure such as setup, migration, or debugging.
- **Reference** — factual commands, contracts, configuration, schemas, and generated file indexes.
- **Explanation** — architecture, rationale, tradeoffs, and domain concepts.

Split a file that mixes these needs. Binding rules may link to all four types but must remain short and explicit.

## Ownership map

| Owner | Contains | Excludes |
| --- | --- | --- |
| Root README | Prerequisites, setup, run, common commands | Architecture narrative |
| Agent entrypoint | Source-tree map, reading order, binding instructions | Duplicated runbook text |
| `docs/README.md` | Trust order, index, current/history labels | Full specifications |
| `docs/architecture/` | Current system, boundaries, data/control flow, decisions | Product backlog |
| `docs/architecture/decisions/` | Small ADRs: Context, Decision, Status, Consequences | Rewritten or erased history |
| `docs/design/` | Product/domain/UI rules appropriate to the project | Runtime setup |
| `docs/CONVENTIONS.md` | Code patterns verified in the checkout | Aspirational style |
| `docs/SECURITY.md` | Binding controls, threat boundaries, known gaps | Generic checklist dumps |
| `docs/TESTING.md` | Suite boundaries, locations, commands, fixtures | General testing philosophy |
| `docs/DEBUG.md` | Repro workflow, known traps, inspection routes | Permanent architecture |
| `docs/OBSERVATION.md` | Logs, health, metrics/tracing scope | Vendor-first shopping list |
| `docs/PLANS.md` | Plan threshold, template, lifecycle, evidence bar | Active task content |
| `docs/LESSONS.md` | Reusable rules paid for by mistakes | One-off bug history |
| `docs/plans/active/` | Multi-session executable work | Completed history |
| `docs/plans/completed/` | Outcomes and abandoned decisions | Current instructions |
| `docs/plans/tech-debt.md` | Known, evidenced, unscheduled gaps | Surprise findings without proof |

Create only owners the project needs. Use folder-level indexes when a directory contains mixed generations or more than a few documents.

Model architecture with **C4** zoom levels and an **arc42 Building Block View**. Link components to source directories and public contracts; route file-level lookup through the generated code index rather than duplicating every file in prose.

## Writing rules

- Write at the owner's altitude.
- Cite code or decisions for non-obvious claims.
- Describe implemented state in present tense; label proposals and future work.
- Prefer commands with expected outcomes over prose instructions.
- Keep one fact in one owner and link to it elsewhere.
- Update the index whenever adding or moving a durable doc.
- Validate relative links after every reorganization.
