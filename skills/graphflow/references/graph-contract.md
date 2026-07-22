# Workflow graph contract

Use [the bundled graph](../assets/workflow-template/graph.json) as the Graphflow v3 schema. Keep `graph.json` as the coordination source of truth; keep reviews, specs, workspaces, progress, and evidence in owned artifacts.

## Poka-Yoke invariants

- **DAG:** dependency and parent graphs are acyclic. An `expanded` node has at least two direct children.
- **MECE:** every required `objective.requirements[].id` is covered exactly once by a non-expansion node.
- **Ownership:** `scope.write`, `scope.artifacts`, and `scope.decisions` are explicit and pairwise disjoint. Reads may overlap. No path globs.
- **Ancestry:** outputs have global IDs; a node consumes only outputs from transitive dependency ancestors.
- **Routing:** ordered `operations` derive project-local `skills`; `graphflow` is never a worker skill.
- **Budget:** positive node budgets sum to at most `constraints.token_budget`.
- **Authority:** caller IDs, leases, schedules, delivery authority, and cost choices stay outside `graph.json`.
- **Dependency Inversion:** each non-expansion node references one locked executor; caller-session bindings are forbidden in the graph and optional at runtime.
- **Shared memory:** coordinator owns `memory/`; nodes submit CAS deltas and may not claim memory artifact paths.
- **Proof-Carrying Work:** coordinator owns `integrity/`; only verify nodes own `evidence/attestations`; executable graphs lock plan and runner digests.
- **YAGNI:** optional discoveries live in root `optional_work`, never cover requirements, and never block completion.
- **Question Triage:** `question_gate` uses Rumsfeld Matrix + Value of Information + Reversibility; executable work has no unresolved pivotal question.

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
  "question_gate": {
    "methods": ["Rumsfeld Matrix", "Value of Information", "Reversibility"],
    "status": "clear",
    "unresolved_pivotal": [],
    "review": {
      "status": "locked",
      "artifact": "question-review.json",
      "digest": "sha256:<review>",
      "graph_digest": "sha256:<question surface>",
      "reviewer_id": "<fresh challenger>"
    }
  },
  "verification": {"outcome": "pending", "claims": []},
  "shared_memory": {
    "schema_version": 1,
    "policy": "blackboard-event-sourcing-v1",
    "state": "memory/state.json",
    "events": "memory/events.jsonl",
    "capsules": "memory/capsules"
  },
  "integrity": {
    "schema_version": 1,
    "level": "medium",
    "status": "locked",
    "verification_plan": "integrity/verification-plan.json",
    "lock": "integrity/lock.json",
    "plan_digest": "sha256:<64 lowercase hex>",
    "runner": "workflow-evidence-runner-v1",
    "runner_digest": "sha256:<64 lowercase hex>",
    "evidence_dir": "evidence/attestations",
    "completion_rule": "all-critical"
  },
  "execution_trust": {
    "schema_version": 1,
    "policy": "risk-adaptive-workspace-v1",
    "workspace_registry": "runtime/workspaces.json",
    "progress_dir": "runtime/progress",
    "required_phases": {
      "low": ["scope_accepted", "evidence_passed"],
      "medium": ["scope_accepted", "evidence_passed", "independently_verified"],
      "high": ["scope_accepted", "evidence_passed", "independently_verified", "externally_verified"]
    }
  }
}
```

For a deterministic exemption use `required: false`, `status: "not_required"`, null manifest/digest/approval, and a concrete `not_required_reason`. See [prototype-gate.md](prototype-gate.md) and [evidence-calibration.md](evidence-calibration.md).
Known pivotal questions use stable IDs plus a non-empty question and controlled impacts. Draft graphs may be `open`; executable and complete graphs require a current locked independent review and must be `clear`. See [question-triage.md](question-triage.md).

## Nodes

| `kind` | Purpose | Required shape |
| --- | --- | --- |
| `expand` | Recursive partition | `operations: ["decomposition"]`, coordinator isolation, no coverage/writes/artifacts/decisions/inputs/outputs |
| `execute` | One bounded outcome | Shared-readonly or worktree isolation |
| `integrate` | Own convergence surface | Includes `integration`; integration isolation |
| `verify` | Falsify integrated claims | Exactly `operations: ["verification"]`; normally read-only; owns evidence artifacts |

Every non-expansion node declares:

```json
{
  "executor": {
    "schema_version": 1,
    "type": "agent",
    "spec": "nodes/B/executor.json",
    "digest": "sha256:<64 lowercase hex>",
    "result": "runtime/results/B.json"
  }
}
```

Use `command` for deterministic scripts and `agent` for bounded model work. Expansion nodes use `executor: null`. See [executor-runtime.md](executor-runtime.md).

Non-expansion status: `pending`, `active`, `waiting_user`, `waiting_approval`, `waiting_external`, `stale`, `blocked`, `complete`, or `failed`. Expansion replaces `complete` with `expanded`. Waiting/active/complete cannot bypass incomplete dependencies. `retry.max_attempts` is always `2`: initial attempt plus one corrected retry.

An active agent executor may return result status `decompose`; this is a proposal, not a graph status. The coordinator may replace that node with an expanded parent and smaller children only under [runtime structural decomposition](runtime-decomposition.md). Generated children carry normative `decomposition_bound: {policy, name, value, source_proposal}`; recursive proposals must continue it. Semantic contract changes remain a user-confirmed rebase.

Each node declares one to three canonical `methods`, ordered primary first. The validator checks the primary method against the first operation; see [method-routing.md](method-routing.md).

## Expansion — MECE + Critical Path

1. Partition independent outcomes, not files or sequential activities.
2. Put shared contracts and irreversible decisions upstream.
3. Give parallel producers disjoint ownership and local acceptance oracles.
4. Add edges only for real artifact or decision handoffs.
5. Reserve shared entrypoints for one integration owner.
6. Stop when one agent can finish the node within budget.

The same stop rule applies at runtime through **Well-Founded Induction**: each automatic split needs a strictly decreasing positive complexity measure and cannot increase the parent budget.

A small objective may use one execute node plus verification. Do not invent parallelism.

## Phase semantics

```bash
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase draft
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase executable --ready
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase complete
```

- `draft`: structure may be incomplete; hard schema/ownership/routing violations still fail.
- `executable`: verification oracle and executor specs are locked, all expansion and coverage are closed, and required prototype is approved, complete, and ancestral to implementation/integration.
- `complete`: every non-expansion node and lifecycle are complete; every requirement has one `verified` claim. `evidence_runner.py validate --phase complete` additionally enforces current attestations, challenge coverage, and independent-review quorum.
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
Use an evidence-backed reversible default for local uncertainty. Ask only for a material contract/baseline decision with no safe default; include triage scope, impacts, affected nodes, and reason. Return only outcome, artifacts/diff, evidence, decisions, blockers/scope request.
```

## Repair table

| Violation | Repair |
| --- | --- |
| Uncovered/duplicate requirement | Add a leaf, atomize, merge, or assign one owner |
| Overlapping path/decision | Move shared ownership upstream or to integration |
| Missing output ancestry | Add the real edge or remove false consumption |
| Budget overflow | Reduce loaded context/scope or merge coordination-heavy nodes |
| Blocked branch | Preserve its requirement claim; never hide it from completion |
