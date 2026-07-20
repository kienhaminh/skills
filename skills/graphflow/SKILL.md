---
name: graphflow
description: Create, edit, and run persistent work graphs. Use only when the user explicitly invokes $graphflow or explicitly asks for a Graphflow workflow.
---

# Run a method-led workflow graph

```text
Explicit ID -> Rumsfeld/MoSCoW -> Prototype Gate -> MECE graph
-> Locked Executors -> Persistent DAG Runner -> Contract Integration -> Falsification
-> Bayesian Calibration -> Authorized Delivery
```

## 1. Explicit ID + Dependency Inversion

Read [automation-lifecycle.md](references/automation-lifecycle.md).

- Create requests derive and return an unused stable kebab-case `workflow_id`.
- Activation/resume requires the exact ID. Resolve with `python3 <skill-dir>/scripts/workflow_state.py resolve .codex/workflows --workflow-id <id>`; never infer it from chat, branch, Goal, or directory.
- Graphflow owns scheduling, recovery, and node execution. Goal may observe, notify, or wake the runner; the runner must never require Goal continuation.
- Keep leases, processes, confirmations, provider sessions, cost choice, and delivery policy outside `graph.json`. Effective authority is user request ∩ executor policy ∩ repository policy.
- Never infer commit, push, PR, merge, deploy, destructive action, credentials, or scope expansion.

For edits to an existing flow, read [flow-editing.md](references/flow-editing.md) and apply **Characterization Testing + Anti-Corruption Layer**. Inspect it first with `reframe_flow.py`. If it passes canonical draft validation, edit it through the gates below. Otherwise create only a digest-bound reframe proposal, present mappings/unknowns/risks, and stop for explicit user confirmation; do not convert, dispatch, edit, or overwrite the source before approval verifies.

## 2. Rumsfeld Matrix + MoSCoW + YAGNI

- Read repository trust-order instructions and current state.
- Record observable objective, atomic required outcomes/acceptance, constraints, non-goals, authority, and pivotal unknowns.
- Route a genuinely fuzzy root through `problem-framing`; do not brainstorm a concrete goal.
- Put non-required discoveries in `optional_work`; they never cover or block requirements.
- Read [question-triage.md](references/question-triage.md). Apply **Rumsfeld Matrix + Value of Information + Reversibility**: resolve pivotal contract unknowns before `ready`; use evidence-backed reversible defaults locally; block only affected branches; never ask about optional work.
- Read [preflight-costing.md](references/preflight-costing.md) only for a hard budget, requested options, or material execution risk/size.

## 3. Prototyping + Falsifiability

Read [prototype-gate.md](references/prototype-gate.md).

- Choose the cheapest credible baseline: static artifact for intent, isolated code prototype for integration, characterization test/dry-run for deterministic work.
- User-visible, subjective, contract/data-changing, or ambiguous work requires user approval. Deterministic approval requires a machine oracle; it is not agent self-approval.
- Freeze the approved digest. Any semantic change needs a concise delta and renewed approval.
- Prototype evidence proves intent only, never product behavior.

## 4. MECE + DRY + Poka-Yoke

Read [graph-contract.md](references/graph-contract.md), [executor-runtime.md](references/executor-runtime.md), [workspace-trust.md](references/workspace-trust.md), [checkout-guard.md](references/checkout-guard.md), and [method-routing.md](references/method-routing.md). Copy [workflow-template](assets/workflow-template) to `.codex/workflows/<id>/`, then adapt `graph.json` and every referenced executor spec.

- Cover every atomic requirement exactly once.
- Give modifiers disjoint write scopes, producers disjoint artifact scopes, and decisions one owner.
- Use named outputs only through dependency ancestry. Put shared contracts upstream and convergence surfaces under one integration owner.
- Expand by outcome, not file or paraphrase. Stop at one bounded owner with a local oracle; do not invent parallelism.
- Give each node one primary and at most two supporting canonical `methods`. Lead with method names, not framework essays.
- Compile each non-expansion node to one digest-locked `command` or `agent` executor. Use argv, never shell text; use the standard result envelope; never embed credentials or chat history.
- Give every modifying node its own registered `worktree` workspace, one convergence node an `integration` workspace, and each verifier a detached `verifier` workspace. Workers never choose paths or commit checkpoints.

```bash
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase draft
python3 <skill-dir>/scripts/question_gate.py lock <workflow-dir>
python3 <skill-dir>/scripts/workspace_manager.py init <workflow-dir>
python3 <skill-dir>/scripts/checkout_guard.py --repo-root <repo> init <workflow-dir>
```

Use one fresh low-cost challenger with artifact-only context for the question review; the coordinator never reviews itself. Re-run and relock it after any question-surface change.

Read [integrity-contract.md](references/integrity-contract.md). Apply **Goodhart's Law + Proof-Carrying Work + Design by Contract**: adapt requirement checks, challenge classes, watched state, and independent verifier roles before broad implementation; then lock the oracle.

```bash
python3 <skill-dir>/scripts/evidence_runner.py lock <workflow-dir> --repo-root <repo>
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase executable --ready
python3 <skill-dir>/scripts/evidence_runner.py validate <workflow-dir> --phase active --repo-root <repo>
```

Never let producers mark their own work verified, manually author attestations, weaken a locked oracle, or compensate a failed critical check with aggregate score. Material oracle changes require a new baseline or explicit user-confirmed supersession.
Do not dispatch until the executable validator passes; it enforces prototype approval/ancestry, oracle lock, semantic method routing, expansion, coverage, ownership, output ancestry, and budget.
Lock executor digests only after graph, scopes, prompts, acceptance checks, model route, and authority are stable. A semantic edit invalidates the digest and returns the workflow to `draft`.

Read [shared-memory.md](references/shared-memory.md). Initialize shared memory after graph adaptation. Keep graph normative, runtime operational, memory epistemic, and evidence external. Rebind memory after every validated graph change.

## 5. Capability Routing + Critical Path

Read [skill-routing.md](references/skill-routing.md) and [subagent-routing.md](references/subagent-routing.md).

- Derive ordered `skills` from `operations`; never route `graphflow` to workers.
- Inspect frontmatter first; load only selected complete skill files when designing or dispatching that node.
- Use cheapest sufficient model/effort. Escalate only after a classified reasoning failure, not environment/authority/external failure.
- Dispatch only ready critical-path or uncertainty-reducing nodes. Parallelize only disjoint ownership and executor workspaces.
- Use shared checkout only for read-only work. Let `workspace_manager.py` provision isolated worktrees, deterministic resource allocations, integration checkpoints, and verifier snapshots.
- Use `fork_turns: "none"` when supported. Pass only methods, node contract, required trust-order files, selected skills, named input artifacts, scopes, acceptance, budget, and return schema—never main chat or worker reasoning.
- Generate a bounded node memory capsule; never pass the whole state/event log. Workers return proposed `memory_delta`; only the coordinator applies it with CAS.

Read [dashboard.md](references/dashboard.md); expose the bundled local read-only projection without duplicating graph state.

## 6. Event Sourcing + PDCA + Recovery

- Start or resume with `python3 <skill-dir>/scripts/run_workflow.py <workflow-dir> --repo-root <repo>`. This is the primary execution loop; do not create a Goal to keep it alive.
- Let the runner acquire the workflow lease, reconcile durable results, execute the ready frontier, validate envelopes and acceptance checks, apply confirmations, and continue until a terminal or waiting state.
- Apply **Zero Trust + TOCTOU + Fail-Closed**: pin the primary checkout before dispatch and recheck it before reconciliation/dispatch, after each parallel frontier, and before Ship. Any drift—including a declared-scope path changed in the primary checkout—pauses consume/delivery until an exact digest-bound adoption is confirmed or the checkout returns to baseline.
- Read [runtime-decomposition.md](references/runtime-decomposition.md). An agent may return a contract-equivalent `decompose` proposal for structural complexity only. Apply **Closed World Assumption + Ranking Function + Fail-Safe Defaults**: preserve terminal acceptance and closed check IDs, continue inherited decreasing bounds, reuse only content-addressed reviews, and verify the Merkle backup before commit/recovery. A pivotal review creates one digest-bound branch rebase request; malformed evidence blocks.
- A branch-scoped waiting node never stops an independent ready frontier; a workflow-scoped baseline question pauses dispatch. Accept a user question only when its triage metadata proves material impact and no safe reversible default; otherwise reject the result for contract repair.
- Accept a handoff only after owned diff/artifacts and coordinator-run acceptance evidence pass. An executor's `succeeded` claim is not acceptance by itself.
- Treat the workflow control plane as **Complete Mediation**: inventory protected directories, reject symlinks, quarantine new files, and restore changed/deleted bytes. For parallel nodes, protect each node's own progress snapshot; peer telemetry may advance concurrently, but completion requires a coordinator-written terminal snapshot.
- Persist outcomes, evidence references, decisions, blockers, and calibrated claims through validated memory deltas; keep routine reasoning internal.
- Transition atomically, append runtime events, revalidate, and dispatch the new frontier.
- Retry once only after shrinking/clarifying the contract. Classify failure: contract, context, reasoning, environment, authority, external.
- On resume reconcile result files, process/session IDs, worktrees, and artifacts. Inspect stale modifying diffs before reassignment. Never erase failed requirement coverage.
- For `waiting_user` or `waiting_approval`, expose the digest-bound request and stop cleanly. Resume only after `confirm_workflow.py` records a matching response; never manufacture approval.
- Let the runner broker missing declared authority before dispatch. Grants are user-confirmed, node-scoped, digest-bound, and revoked on terminal handoff; never let a worker self-grant.

## 7. Contract Testing + Popperian Falsification

Integrate only accepted outputs. Give a fresh verifier requirements, approved baseline, locked checks, integrated artifacts, and known limits—no producer reasoning. Run checks only through `evidence_runner.py run`. The verifier returns a bounded claim/review proposal; the coordinator validates current attestations, records the review, and writes graph claims. Read [evidence-calibration.md](references/evidence-calibration.md); record `verified`, `observed`, `inferred`, or `unverified` claims.

```bash
python3 <skill-dir>/scripts/evidence_runner.py validate <workflow-dir> --phase complete --repo-root <repo>
python3 <skill-dir>/scripts/memory_state.py validate <workflow-dir> --phase complete --check-artifacts
```

Completion is non-compensatory: every critical check must have a current runner attestation, required challenge classes and verifier quorum must pass, required claims must cite matching attestations, scope remains valid, and baseline/non-goal drift is absent. `complete_with_limits` applies only to extra non-required claims; a required unverified claim blocks completion.

## 8. Outcome-Only delivery

Read [delivery-contract.md](references/delivery-contract.md) and the current project-local `ship` skill at `.codex/skills/ship/SKILL.md`. Apply its **Gate → Record → Commit → Publish** order.

- Keep analysis, scheduling, polling, retries, and routine transitions internal.
- Ask only for material intent/baseline, authority, cost-risk, or irreversible decisions.
- Report material scope/risk reversals, workflow-wide blockers, delivery-readiness changes, and completion.
- Perform only authorized delivery; never auto-merge/deploy without separate authority.
- When commit/push/PR is requested, model `Ship Gate -> Record -> release integration -> independent verification -> broker`. Gate uses the current Ship playbook's applicable type-check, scoped-test, `/verify`, and `/code-review` checks. The coordinator broker then squashes the exact verified tree onto pinned `origin/master`, requests one manifest-bound approval, pushes the exact release SHA, proves the remote ref, and creates/reuses the PR idempotently. Workers never publish or receive credentials.
- Treat internal worktree checkpoint commits as recovery artifacts, not the Ship commit. Never force-push, publish after base drift, or infer merge/deploy authority.
- Final report: outcome/artifact or PR, acceptance evidence, changed scope, calibrated claims/limits, cost variance, and deferred optional work. Omit worker history unless asked.
- Clear owned leases, stop owned dashboard processes, retain evidence, and archive completed artifacts when safe.
