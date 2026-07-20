# Brownfield flow editing — Strangler Fig + Anti-Corruption Layer

Treat the existing flow as source material, not automatically as a Graphflow graph.

## Characterization gate

Inspect without changing the source:

```bash
python3 <skill-dir>/scripts/reframe_flow.py inspect <flow-file-or-workflow-dir> \
  --output <artifact-dir>/reframe/proposal.json [--workflow-id <id>]
```

- `canonical-graphflow-v3`: `graph.json` passes draft validation. Edit that workflow in place through its normal question, prototype, scope, workspace, memory, oracle-lock, and delivery gates.
- `noncanonical-structured` or `opaque`: use **Anti-Corruption Layer + MECE + Rumsfeld Matrix** to complete every `reframe_mapping` field for objective/non-goals, atomic requirements, nodes/edges, scopes, prototype gate, oracles, unknowns, and discarded semantics. Do not convert, edit, dispatch, or overwrite the source.

For a canonical flow, apply **Change Impact Analysis**: operational status/runtime updates use `workflow_state.py`; semantic edits to objective, requirements, nodes, ownership, intent, or oracles must preserve the locked version, create a new revision baseline, and re-run prototype/oracle gates. Never hand-edit a locked contract or erase its evidence history.

## Digest-bound confirmation

Hash the completed proposal, then present it with material semantic changes, unresolved mappings, risks, and `proposal_digest`. Ask the user to approve that exact reframe. After explicit approval, record:

```json
{
  "schema_version": 1,
  "proposal_digest": "sha256:<digest shown to user>",
  "decision": "approved",
  "approved_by": "user",
  "approved_at": "<timestamp>"
}
```

Verify before conversion:

```bash
python3 <skill-dir>/scripts/reframe_flow.py verify-approval \
  <proposal.json> <approval.json>
```

Any proposal change invalidates approval. After approval, build a canonical sibling artifact with **Strangler Fig Pattern**; preserve the original until the new graph passes draft/executable validation and the user-authorized cutover. Never silently reinterpret missing semantics.

For Graphflow v1/v2, create a sibling v3 artifact with `migrate_workflow.py <source> --output <target>`. The migration preserves the source, resets semantic locks, adds registered workspaces/progress trust, updates result contracts/digests, and requires a fresh question review plus integrity relock before cutover.
