# Shared memory — Blackboard + Event Sourcing

Keep shared workflow memory separate from agent memory and graph/runtime state:

| Source | Authority |
| --- | --- |
| `graph.json` | Normative objective, scope, dependencies, acceptance |
| `runtime.json` | Agents, leases, processes, worktrees |
| `memory/state.json` | Materialized epistemic state |
| `memory/events.jsonl` | Append-only recovery/audit log |
| `integrity/` | Locked oracle and independent-review records |
| `evidence/` | Full proof; memory stores only path and digest |

Memory cannot silently change graph scope, requirements, authority, or intent. Rebind a validated graph change explicitly.

## Single Writer + MVCC/CAS

Initialize after adapting the graph:

```bash
python3 <skill-dir>/scripts/memory_state.py init <workflow-dir>
python3 <skill-dir>/scripts/memory_state.py validate <workflow-dir>
```

Workers never mutate shared state. Give each worker a selective capsule:

```bash
python3 <skill-dir>/scripts/memory_state.py view <workflow-dir> --node <id>
```

Workers return a `memory_delta` with `base_revision`, `author_node`, additions, supersessions, and resolutions. The coordinator applies it:

```bash
python3 <skill-dir>/scripts/memory_state.py apply-delta <workflow-dir> <delta.json>
```

CAS rejects stale revisions. Node deltas may write only `node.<id>` or owned decision namespaces and reference only artifacts inside owned scopes. Coordinator is the sole cross-namespace writer.

## Least Context

Store only `fact`, `decision`, `risk`, `question`, `learning`, or `handoff` entries. Keep summaries under 500 characters; reference artifacts by SHA-256. Only verify nodes may publish `verified` entries, backed by passing evidence-runner attestations; producers use `observed` or lower. Never store chain-of-thought, transcripts, source/test payloads, credentials, environment values, or state derivable from graph/runtime.

For local uncertainty, record only the chosen evidence-backed reversible assumption and affected nodes. Material questions use the runtime confirmation broker; after resolution, store the decision rather than the question transcript. Active pivotal questions still block completion.

Capsules rank pivotal entries, explicit relevance, requirement matches, node ownership, and dependency ancestry; default output is bounded. Any revision change invalidates materialized capsules, so regenerate immediately before dispatch. Pass the capsule, never the whole state/event log.

## Recovery + completion

```bash
python3 <skill-dir>/scripts/memory_state.py replay <workflow-dir> --check
python3 <skill-dir>/scripts/memory_state.py compact <workflow-dir>
python3 <skill-dir>/scripts/memory_state.py bind-graph <workflow-dir>
python3 <skill-dir>/scripts/memory_state.py validate <workflow-dir> --phase complete --check-artifacts
```

- Append event before atomically replacing the snapshot; replay repairs interrupted materialization.
- Compact resolved/superseded entries from the snapshot; retain the log.
- `bind-graph` records a new semantic graph digest and revision after graph validation.
- Complete phase rejects conflicting active decision/handoff namespaces and active pivotal questions.
