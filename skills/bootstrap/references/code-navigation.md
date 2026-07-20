# Token-efficient code navigation

Regenerate navigation evidence from the current checkout. Do not substitute memory, prose summaries, or an old index for live symbols and configuration.

## Progressive read set

Use Information Foraging terms directly:

1. **Information need:** express the task with domain nouns, runtime surface, and expected behavior.
2. **Information scent:** search paths, symbols, contracts, route/job names, config keys, tests, and error text.
3. **Topology:** follow imports, registrations, callers, implementations, and test edges.
4. **Patch boundary:** stop expanding when the behavior, owners, consumers, and verification path are accounted for.

Read in this order unless evidence redirects the search:

`entrypoint → public contract → registration/composition → implementation → tests → config/schema → owning docs`

Never read every file sequentially. Never load a generated full index into context when a ranked query can return the relevant slice.

## Navigation precision ladder

| Priority | Mechanism | Trust |
| --- | --- | --- |
| 1 | Compiler, LSP, SCIP | Exact definitions/references for the configured build |
| 2 | Build/workspace graph | Exact package and task ownership |
| 3 | Tree-sitter, ctags | Structural symbols; may lack type resolution |
| 4 | Generated file index | Deterministic per-file routing and keywords |
| 5 | `rg` | Fast lexical evidence; misses dynamic relations |
| 6 | Docs or memory | Routing hints only; verify against higher layers |

Use search-based navigation immediately; add SCIP only when repository size, cross-repository references, or repeated navigation cost justifies indexer maintenance.

## Per-file record

Generate one record for every supported source file:

```json
{
  "path": "apps/server/src/publish/publish.service.ts",
  "language": "typescript",
  "role": "service",
  "lines": 180,
  "sha256": "checkout-derived",
  "keywords": ["publish", "snapshot", "service"],
  "symbols": [{"name": "PublishService", "kind": "class", "line": 21}],
  "imports": ["@acme/db", "./common/publish-policy"],
  "referenced_by": ["apps/server/src/publish/publish.controller.ts"],
  "related_tests": ["apps/server/src/publish/publish.service.spec.ts"]
}
```

Keep records factual. Do not generate semantic prose such as “handles all publishing logic”; that claim drifts and costs tokens. Derive meaning by reading the selected source slice.

## File-level ownership

For each source file selected for change, account for:

- its public symbols and entrypoint reachability;
- inbound and outbound dependencies;
- runtime registration or discovery mechanism;
- nearest unit/integration/end-to-end tests;
- owning config, schema, migration, contract, and docs;
- generated status and regeneration command;
- security, deployment, and compatibility consequences.

If any relationship is unknown, preserve the file or expand the search. “No textual references” is not equivalent to “unused.”

## Freshness

- Use content hashes to detect changed records.
- Regenerate after moves, renames, dependency changes, or generated-code updates.
- Keep the index local/ignored by default.
- Commit an index only when CI verifies regeneration and the repository declares it authoritative.
