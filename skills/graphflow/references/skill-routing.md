# Local skill routing

Operations are semantic; project-local skills are deterministic. Inspect frontmatter while designing, then read each selected `SKILL.md` completely only when its node is ready. A missing mandatory skill is a graph-design blocker, not permission to improvise its contract.

## Mandatory mapping

Ordered `skills` must equal the mapped non-empty values from ordered `operations`:

| Operation | Project-local skill | Use |
| --- | --- | --- |
| `problem-framing` | `brainstorming` | Fuzzy, multi-variable root question |
| `feature-plan` | `grill-me` | Concrete product/feature requirements |
| `story-slicing` | `to-stories` | Vertical observable slices |
| `test-design` | `to-tdd` | Executable behavior/test plan |
| `implementation` | `implement` | Authorized code change and focused checks |
| `diagnosis` | `debugging` | Evidence-first diagnosis; no fix unless separately authorized |
| `docs-sync` | `sync-docs` | Canonical documentation reconciliation |
| `bootstrap` | `bootstrap` | Repo scaffold/initial structure |
| `worktree-management` | `worktree` | Isolated modifying checkout |
| `analysis`, `decomposition`, `prototyping`, `integration`, `verification` | none | Workflow contract supplies the procedure |

Examples:

```json
{"operations":["test-design","implementation"],"skills":["to-tdd","implement"]}
{"operations":["integration","implementation"],"skills":["implement"]}
{"operations":["verification"],"skills":[]}
```

Never include coordinator skill `graphflow` in a node.

`ship` is coordinator-owned. A bounded Record node may use its Record rules, but commit/push/PR are executed only by Graphflow's delivery broker after final verification; never route Publish credentials or Git-ref mutation to a worker.

## Composition rules

- Compose operations in one node when they share write ownership or one acceptance oracle.
- Split only at a durable named output and disjoint ownership boundary.
- `problem-framing` precedes graph decomposition only when the root is genuinely fuzzy; do not run it for every objective.
- `feature-plan` is not decomposition: it resolves requirement choices before MECE graphing.
- `diagnosis` may precede `implementation`; diagnosis itself remains non-mutating unless the caller authorized a fix.
- `verification` stays independent from producer implementation even when the same test skill informed design.

## Selection order

1. Repository `AGENTS.md` and trust-order docs.
2. Mandatory project-local skill from the table.
3. Relevant installed domain skill only when its capability materially changes the node contract.
4. Generic method procedure when no skill is required.

Do not load every local skill. Record selected skill paths in the node prompt; keep unused skill bodies out of context.

## Capability gaps

When a required capability has no available skill/tool, keep the node blocked or redesign it. Installing a plugin, using credentials, network access, or expanding repository scope follows caller authority; workflow routing never grants it implicitly.
