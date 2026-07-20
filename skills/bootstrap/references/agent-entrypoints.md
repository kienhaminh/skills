# Coding-agent entrypoints

Use this contract whenever creating or updating root `AGENTS.md` and `CLAUDE.md`.

## Required layout

Keep both files compact because they enter every session prompt. Order shared sections as:

1. `# Repository operating guide`
2. `## Source tree`
3. the canonical core block below, copied byte-for-byte including markers;
4. `## Source-of-truth routing`;
5. `## Canonical commands`;
6. `## Repository-specific rules`;
7. optional, minimal tool-specific protocol.

Always render `## Source tree` from the completed checkout, after source, configuration, tooling, tests, CI, and durable docs are finalized. Show entrypoints, bounded contexts or packages, shared contracts, tests, infrastructure, and documentation owners; omit generated, dependency, cache, and build-output trees. Expand `docs/` to list every durable top-level document owner and routing directory. Annotate ownership or purpose briefly. Never reuse a stale or pre-setup tree merely because one already exists.

## Finalization order

Apply `Setup → Document → Verify → Stabilize → Index → Render`:

1. Read existing entrypoints early for binding constraints; defer rewriting them.
2. Complete source, configuration, tooling, tests, infrastructure, CI, cleanup, and restructuring.
3. Create and validate the complete documentation system.
4. Run supported gates and repair all durable files until no planned structural or docs changes remain.
5. Regenerate the final code index from the stable checkout.
6. Render the source tree, then merge the final shared guide into both entrypoints.
7. Run non-mutating entrypoint, link, and drift checks. If any later fix changes a durable path or doc, repeat steps 5–7.

## Merge protocol

Apply `Read → Extract → Compare → Merge → Verify`:

1. Read both existing files completely before writing either one.
2. Extract their source tree, shared rules, repository-specific rules, and tool-specific protocol.
3. Compare each rule by intent, scope, authority, and current checkout evidence.
4. Replace equivalent shared rules with the canonical wording below; retain stricter compatible details under repository-specific rules.
5. Preserve non-conflicting user or repository instructions. Move a rule only when its scope becomes clearer.
6. Do not silently resolve a real conflict. Preserve the authoritative existing rule, record the conflict, and ask only when it materially changes behavior.
7. Keep shared sections identical. Put a necessary Claude-only delta in `CLAUDE.md` under `## Claude-specific protocol`; declare the reason and owner.
8. Refresh source-tree paths, commands, and links from final live evidence; remove superseded text only after proving it stale.

## Canonical core block

<!-- bootstrap:core:start -->
## Core working principles

- **Source Before Memory** — Trust the current checkout, runtime evidence, and authoritative repository docs over recalled context.
- **Evidence First** — Separate `Observed`, `Requested`, and `Proposed`; never present an inference or plan as implemented fact.
- **Smallest Sufficient Read Set** — Start from the source tree and owning entrypoint, then follow symbols, tests, and configuration only as needed.
- **Search → Reuse → Extend → Localize → Extract** — Search semantic owners before adding a function, component, class, hook, service, type, or module.
- **Observe → Hypothesize → Falsify → Decide → Verify** — Make the smallest testable claim, seek disconfirming evidence, then act.
- **KISS → YAGNI → AHA → Rule of Three** — Prefer the simplest correct design; tolerate small duplication before creating a premature abstraction.
- **Narrowest Responsible Owner** — Place behavior with the cohesive domain owner and preserve dependency direction; avoid generic dumping grounds.
- **Contract → Tests → Implementation** — Protect public behavior and failure modes before structural or risky changes.
- **Characterize → Migrate → Verify → Delete** — Prove ownership and replacement before removing code, data, migrations, assets, tooling, or infrastructure.
- **Scope Discipline** — Preserve unrelated user work, avoid opportunistic rewrites, and keep changes reversible and reviewable.
- **Verify, Then Claim** — Run the narrowest relevant checks first, report unrun gates honestly, and never claim readiness without evidence.
<!-- bootstrap:core:end -->

Copy this block exactly. Add repository detail outside its markers; never fork or paraphrase the canonical core inside either entrypoint.
