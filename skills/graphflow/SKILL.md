---
name: graphflow
description: Create and run persistent, verified coding-work graphs across tools through digest-locked adapters and optional delivery.
disable-model-invocation: true
---

# Run a persistent coding workflow graph

Graphflow stores tool-neutral state under `.graphflow/`. Agent nodes run through an explicit adapter;
the core speaks only the neutral process contract while each wrapper owns its tool's CLI, model IDs,
and session lifecycle. The runner owns scheduling, recovery, node execution, and durable state; the
coordinator owns graph design, authority, integration, acceptance, and delivery.

## 1. Resolve identity and authority

Read [automation-lifecycle.md](references/automation-lifecycle.md). Create an unused stable
`workflow_id`, or require the exact ID to activate or resume an existing workflow:

```bash
python3 <skill-dir>/scripts/workflow_state.py resolve .graphflow/workflows --workflow-id <id>
```

Effective authority is the intersection of the user request, executor policy, and repository policy.
Record commit, push, pull request, merge, deploy, destructive, network, and credential capabilities
separately. Complete this phase when identity, objective, authority, and lifecycle state are
unambiguous.

If delivery is required, read [delivery-contract.md](references/delivery-contract.md) now. Prove the
configured adapter, hosting repository, remote, hostname, and available authentication route before
any executor dispatch; an unsupported provider or unavailable authorized preflight is a
`waiting_external` terminal, not a late Publish discovery.

For an existing noncanonical flow, read [flow-editing.md](references/flow-editing.md). Produce a
digest-bound reframe proposal and wait for approval before conversion. A canonical flow proceeds
through the remaining gates.

## 2. Close pivotal uncertainty

Record observable objective, atomic requirements and acceptance, constraints, non-goals, authority,
and pivotal unknowns. Route a genuinely fuzzy root through the installed `brainstorming` skill; route
a concrete feature brief through `grill-me`. Missing required skills are design blockers under
[skill-routing.md](references/skill-routing.md).

Read [question-triage.md](references/question-triage.md). Resolve pivotal contract unknowns before
`ready`, use evidence-backed reversible defaults for local uncertainty, and isolate branch-scoped
questions. Read [preflight-costing.md](references/preflight-costing.md) only for a hard budget,
requested options, or material execution risk.

Complete this phase when `question_gate` is locked, clear, and has no unresolved pivotal question.

## 3. Freeze the intent baseline

Read [prototype-gate.md](references/prototype-gate.md). Use the cheapest credible artifact:
wireframe for subjective intent, isolated prototype for integration, characterization test for
behavior, or dry-run for deterministic automation. Bind approval to the artifact digest; treat static
or mocked evidence as intent proof only.

Complete this phase when the approved digest and limitations are recorded, or a deterministic
exemption has a concrete machine-checkable reason.

## 4. Compile an executable graph

Read [graph-contract.md](references/graph-contract.md),
[executor-runtime.md](references/executor-runtime.md),
[workspace-trust.md](references/workspace-trust.md),
[checkout-guard.md](references/checkout-guard.md), and
[method-routing.md](references/method-routing.md), and [tool-adapters.md](references/tool-adapters.md).
Copy [workflow-template](assets/workflow-template) to `.graphflow/workflows/<id>/`, configure one
digest-locked agent adapter when the graph has agent executors, then adapt every normative
artifact.

- Cover every atomic requirement exactly once.
- Give writes, artifacts, and decisions one disjoint owner.
- Pass named outputs only through dependency ancestry.
- Expand by bounded outcome; parallelize only disjoint ownership.
- Compile each leaf to one digest-locked command or agent executor with a local oracle.
- Register modifying, integration, and verifier workspaces separately.

```bash
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase draft
python3 <skill-dir>/scripts/question_gate.py lock <workflow-dir>
python3 <skill-dir>/scripts/workspace_manager.py init <workflow-dir>
python3 <skill-dir>/scripts/checkout_guard.py --repo-root <repo> init <workflow-dir>
```

Read [integrity-contract.md](references/integrity-contract.md), adapt requirement checks and
independent verifier roles, then lock the oracle:

```bash
python3 <skill-dir>/scripts/evidence_runner.py lock <workflow-dir> --repo-root <repo>
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase executable --ready
python3 <skill-dir>/scripts/evidence_runner.py validate <workflow-dir> --phase active --repo-root <repo>
```

Read [shared-memory.md](references/shared-memory.md) and initialize bounded coordinator-owned memory.
Complete compilation only when executable validation passes and all executor, question, intent,
workspace, memory, and oracle locks match the same semantic graph.

## 5. Route and run

Read [skill-routing.md](references/skill-routing.md) and
[subagent-routing.md](references/subagent-routing.md). Derive node skills from operations, pass only
the node contract and named artifacts, and use the cheapest sufficient executor. Read
[dashboard.md](references/dashboard.md) only when a local read-only projection is useful.

```bash
python3 <skill-dir>/scripts/run_workflow.py <workflow-dir> --repo-root <repo>
```

Let the runner acquire the lease, reconcile durable state, check the primary checkout, execute the
ready frontier, validate result envelopes, run acceptance checks, and continue to a terminal or
waiting state. Read [runtime-decomposition.md](references/runtime-decomposition.md) when an agent
returns a structural decomposition proposal. Preserve failed coverage and retry once only after a
classified contract repair.

Execution is complete when the runner reaches an honest terminal or digest-bound waiting state with
no unaccounted live executor.

## 6. Verify and deliver

Give a fresh verifier the requirements, approved baseline, locked checks, integrated artifacts, and
known limits. Read [evidence-calibration.md](references/evidence-calibration.md) and record each claim
as `verified`, `observed`, `inferred`, or `unverified`.

```bash
python3 <skill-dir>/scripts/evidence_runner.py validate <workflow-dir> --phase complete --repo-root <repo>
python3 <skill-dir>/scripts/memory_state.py validate <workflow-dir> --phase complete --check-artifacts
```

Every required claim needs a current critical attestation; aggregate score cannot compensate for a
failed requirement.

When delivery is authorized, read [delivery-contract.md](references/delivery-contract.md) and the
installed `ship` skill. Preserve **Gate → Record → Commit → Publish**, discover the remote and base
branch from repository evidence, and bind one approval to the exact verified tree. Merge and deploy
remain separate authority.

Finish with outcome or PR, requirement-level evidence, changed scope, calibrated limitations, cost
variance, and deferred optional work. Clear owned leases and processes while retaining evidence
needed for recovery or review.
