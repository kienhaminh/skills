# Workflow graph contract

Use [the bundled graph](../assets/workflow-template/graph.json) as the full schema. Keep `graph.json` as the coordination source of truth; keep specs and evidence in owned artifacts.

## Poka-Yoke invariants

- **DAG:** dependency and parent graphs are acyclic. An `expanded` node has at least two direct children.
- **MECE:** every required `objective.requirements[].id` is covered exactly once by a non-expansion node.
- **Ownership:** `scope.write`, `scope.artifacts`, and `scope.decisions` are explicit and pairwise disjoint. Reads may overlap. No path globs.
- **Ancestry:** outputs have global IDs; a node consumes only outputs from transitive dependency ancestors.
- **Routing:** ordered `operations` derive project-local `skills`; `workflow` is never a worker skill.
- **Budget:** positive node budgets sum to at most `constraints.token_budget`.
- **Authority:** caller IDs, leases, schedules, delivery authority, and cost choices stay outside `graph.json`.
- **Shared memory:** coordinator owns `memory/`; nodes submit CAS deltas and may not claim memory artifact paths.
- **YAGNI:** optional discoveries live in root `optional_work`, never cover requirements, and never block completion.

## Root gates

Every graph contains:

```json
{
  "intent_baseline": {
    "required": true,
    "status": "approved",
    "manifest": "prototype/manifest.json",
    "digest": "sha256:<64 lowercase hex>",
    "approval": "user",
    "not_required_reason": null
  },
  "verification": {"outcome": "pending", "claims": []},
  "shared_memory": {
    "schema_version": 1,
    "policy": "blackboard-event-sourcing-v1",
    "state": "memory/state.json",
    "events": "memory/events.jsonl",
    "capsules": "memory/capsules"
  }
}
```

For a deterministic exemption use `required: false`, `status: "not_required"`, null manifest/digest/approval, and a concrete `not_required_reason`. See [prototype-gate.md](prototype-gate.md) and [evidence-calibration.md](evidence-calibration.md).

## Nodes

| `kind` | Purpose | Required shape |
| --- | --- | --- |
| `expand` | Recursive partition | `operations: ["decomposition"]`, coordinator isolation, no coverage/writes/artifacts/decisions/inputs/outputs |
| `execute` | One bounded outcome | Shared-readonly or worktree isolation |
| `integrate` | Own convergence surface | Includes `integration`; integration isolation |
| `verify` | Falsify integrated claims | Exactly `operations: ["verification"]`; normally read-only; owns evidence artifacts |

Non-expansion status: `pending`, `active`, `waiting_user`, `waiting_approval`, `waiting_external`, `stale`, `blocked`, `complete`, or `failed`. Expansion replaces `complete` with `expanded`. Waiting/active/complete cannot bypass incomplete dependencies. `retry.max_attempts` is always `2`: initial attempt plus one corrected retry.

Each node declares one to three canonical `methods`, ordered primary first. The validator checks the primary method against the first operation; see [method-routing.md](method-routing.md).

## Expansion — MECE + Critical Path

1. Partition independent outcomes, not files or sequential activities.
2. Put shared contracts and irreversible decisions upstream.
3. Give parallel producers disjoint ownership and local acceptance oracles.
4. Add edges only for real artifact or decision handoffs.
5. Reserve shared entrypoints for one integration owner.
6. Stop when one agent can finish the node within budget.

A small objective may use one execute node plus verification. Do not invent parallelism.

## Phase semantics

```bash
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase draft
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase executable --ready
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase complete
```

- `draft`: structure may be incomplete; hard schema/ownership/routing violations still fail.
- `executable`: all expansion and coverage are closed; required prototype is approved, complete, and ancestral to implementation/integration.
- `complete`: every non-expansion node and lifecycle are complete; every requirement has one directly evidenced `verified` claim.
- `lifecycle.status: complete` means required outcomes passed. `verification.outcome: complete_with_limits` means only additional, non-required claims remain limited.

## Compact worker contract

```text
Methods: <primary> -> <supporting>. Apply to <one decision/check>.
Node <id>: <bounded outcome>. Objective/non-goals: <one line>.
Trust order: <required instruction paths>. Skills: <selected paths>.
Inputs: <output id -> artifact + verified summary>.
Read: <paths>. Exclusive writes/artifacts/decisions: <paths/names>.
Forbidden: <paths/actions>. Acceptance: <checks>. Budget: <tokens>.

Work independently; do not reconstruct parent chat. Stop on scope insufficiency.
Return only outcome, artifacts/diff, evidence, decisions, blockers/scope request.
```

## Repair table

| Violation | Repair |
| --- | --- |
| Uncovered/duplicate requirement | Add a leaf, atomize, merge, or assign one owner |
| Overlapping path/decision | Move shared ownership upstream or to integration |
| Missing output ancestry | Add the real edge or remove false consumption |
| Budget overflow | Reduce loaded context/scope or merge coordination-heavy nodes |
| Blocked branch | Preserve its requirement claim; never hide it from completion |
