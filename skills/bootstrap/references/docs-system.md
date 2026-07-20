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
| Docs index | Trust order, owners, current/history labels | Full specifications |
| Architecture owner | Current system, boundaries, data/control flow, decisions | Product backlog |
| Decision log | Small ADRs: Context, Decision, Status, Consequences | Rewritten or erased history |
| Product/domain owner | Product, domain, and UI rules | Runtime setup |
| Convention owner | Code patterns verified in the checkout | Aspirational style |
| Security owner | Binding controls, threat boundaries, known gaps | Generic checklist dumps |
| Testing owner | Suite boundaries, commands, fixtures | General testing philosophy |
| Debugging owner | Reproduction, known traps, inspection routes | Permanent architecture |
| Operations owner | Logs, health, metrics, tracing, runbooks | Vendor-first shopping list |
| Planning owner | Plan threshold, lifecycle, active/completed work, debt | Durable architecture |

Create only owners the project needs. Use folder-level indexes when a directory contains mixed generations or more than a few documents.

Model architecture with **C4** zoom levels and an **arc42 Building Block View**. Link components to source directories and public contracts; route file-level lookup through the generated code index rather than duplicating every file in prose.

## Coding-agent entrypoints

Discover the coding-agent entrypoints already owned by the repository. Preserve them and keep shared
facts linked to one authoritative owner. Create a new entrypoint only when the user requests it or the
selected agent tooling requires it. When creating or synchronizing entrypoints, follow
[agent-entrypoints.md](agent-entrypoints.md) as the merge contract.

Use one compact shared operating map:

- current source tree and boundary ownership;
- trust order and smallest first-read set;
- canonical setup, run, test, lint, build, and inspection commands;
- binding reuse, convention, security, testing, debugging, and cleanup gates;
- repository-specific safety constraints and links to their authoritative owners.

Read existing entrypoints before setup, but render any final source tree only after source and durable
docs are stable. When a synchronized set is in scope, keep repository-owned shared sections aligned.
Isolate tool-specific protocol under a named section with an owner and deterministic drift check.

When the repository already uses `AGENTS.md` or `CLAUDE.md`, add a nested file only for a real
subtree-scoped override. State scope and inheritance explicitly and keep shared rules in the root
owner.

## Writing rules

- Write at the owner's altitude.
- Cite code or decisions for non-obvious claims.
- Describe implemented state in present tense; label proposals and future work.
- Prefer commands with expected outcomes over prose instructions.
- Keep one fact in one owner and link to it elsewhere.
- Keep every repository-owned coding-agent entrypoint accurate; when a synchronized pair exists,
  verify its shared content cannot drift silently.
- Update the index whenever adding or moving a durable doc.
- Validate relative links after every reorganization.
