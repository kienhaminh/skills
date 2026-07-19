---
name: workflow
description: Create or run a provider-neutral persistent work graph identified by workflow_id, with machine-enforced intent, MECE ownership, selective shared memory, local skill/subagent routing, recovery, falsification, calibrated evidence, integration, and caller-authorized delivery. Use when the user invokes $workflow, asks for a reusable workflow, or starts/resumes a Goal, loop, or manual run that explicitly supplies workflow_id.
---

# Run a method-led workflow graph

```text
Explicit ID -> Rumsfeld/MoSCoW -> Prototype Gate -> MECE graph
-> Critical Path -> Contract Integration -> Popperian Falsification
-> Bayesian Calibration -> Authorized Delivery
```

## 1. Explicit ID + Separation of Concerns

Read [automation-lifecycle.md](references/automation-lifecycle.md).

- Create requests derive and return an unused stable kebab-case `workflow_id`.
- Activation/resume requires the exact ID. Resolve with `python3 <skill-dir>/scripts/workflow_state.py resolve .codex/workflows --workflow-id <id>`; never infer it from chat, branch, Goal, or directory.
- Caller owns Goal/loop lifecycle and authority. Keep bindings, leases, schedules, cost choice, and delivery policy out of `graph.json`.
- Effective authority is the intersection of user, caller, and repository policy. Never infer commit, push, PR, merge, deploy, destructive action, credentials, or scope expansion.

## 2. Rumsfeld Matrix + MoSCoW + YAGNI

- Read repository trust-order instructions and current state.
- Record observable objective, atomic required outcomes/acceptance, constraints, non-goals, authority, and pivotal unknowns.
- Route a genuinely fuzzy root through `problem-framing`; do not brainstorm a concrete goal.
- Put non-required discoveries in `optional_work`; they never cover or block requirements.
- Read [preflight-costing.md](references/preflight-costing.md) only for a hard budget, requested options, or material execution risk/size.

## 3. Prototyping + Falsifiability

Read [prototype-gate.md](references/prototype-gate.md).

- Choose the cheapest credible baseline: static artifact for intent, isolated code prototype for integration, characterization test/dry-run for deterministic work.
- User-visible, subjective, contract/data-changing, or ambiguous work requires user approval. Deterministic approval requires a machine oracle; it is not agent self-approval.
- Freeze the approved digest. Any semantic change needs a concise delta and renewed approval.
- Prototype evidence proves intent only, never product behavior.

## 4. MECE + DRY + Poka-Yoke

Read [graph-contract.md](references/graph-contract.md) and [method-routing.md](references/method-routing.md). Copy [workflow-template](assets/workflow-template) to `.codex/workflows/<id>/`, then adapt `graph.json`.

- Cover every atomic requirement exactly once.
- Give modifiers disjoint write scopes, producers disjoint artifact scopes, and decisions one owner.
- Use named outputs only through dependency ancestry. Put shared contracts upstream and convergence surfaces under one integration owner.
- Expand by outcome, not file or paraphrase. Stop at one bounded owner with a local oracle; do not invent parallelism.
- Give each node one primary and at most two supporting canonical `methods`. Lead with method names, not framework essays.

```bash
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase draft
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase executable --ready
```

Do not dispatch until the executable validator passes; it enforces prototype approval/ancestry, semantic method routing, expansion, coverage, ownership, output ancestry, and budget.

Read [shared-memory.md](references/shared-memory.md). Initialize shared memory after graph adaptation. Keep graph normative, runtime operational, memory epistemic, and evidence external. Rebind memory after every validated graph change.

## 5. Capability Routing + Critical Path

Read [skill-routing.md](references/skill-routing.md) and [subagent-routing.md](references/subagent-routing.md).

- Derive ordered `skills` from `operations`; never route `workflow` to workers.
- Inspect frontmatter first; load only selected complete skill files when designing or dispatching that node.
- Use cheapest sufficient model/effort. Escalate only after a classified reasoning failure, not environment/authority/external failure.
- Dispatch only ready critical-path or uncertainty-reducing nodes. Parallelize only disjoint ownership.
- Use shared checkout for read-only work, isolated worktrees for parallel modifiers, and one integration owner.
- Use `fork_turns: "none"` when supported. Pass only methods, node contract, required trust-order files, selected skills, named input artifacts, scopes, acceptance, budget, and return schema—never main chat or worker reasoning.
- Generate a bounded node memory capsule; never pass the whole state/event log. Workers return proposed `memory_delta`; only the coordinator applies it with CAS.

Read [dashboard.md](references/dashboard.md); expose the bundled local read-only projection without duplicating graph state.

## 6. PDCA + Recovery

- Accept a handoff only after owned diff/artifacts and acceptance evidence pass.
- Persist outcomes, evidence references, decisions, blockers, and calibrated claims through validated memory deltas; keep routine reasoning internal.
- Transition atomically, revalidate, and dispatch the new frontier.
- Retry once only after shrinking/clarifying the contract. Classify failure: contract, context, reasoning, environment, authority, external.
- On resume reconcile live agents, worktrees, processes, and artifacts. Inspect stale modifying diffs before reassignment. Never erase failed requirement coverage.

## 7. Contract Testing + Popperian Falsification

Integrate only accepted outputs. Give a fresh verifier requirements, approved baseline, integrated artifacts, and known limits—no producer reasoning. Read [evidence-calibration.md](references/evidence-calibration.md); record machine-checked `verified`, `observed`, `inferred`, or `unverified` claims.

```bash
python3 <skill-dir>/scripts/validate_graph.py <graph.json> --phase complete
python3 <skill-dir>/scripts/memory_state.py validate <workflow-dir> --phase complete --check-artifacts
```

Complete only when required nodes and claims are directly verified, scope remains valid, and baseline/non-goal drift is absent. `complete_with_limits` applies only to extra non-required claims; a required unverified claim blocks completion.

## 8. Outcome-Only delivery

- Keep analysis, scheduling, polling, retries, and routine transitions internal.
- Ask only for material intent/baseline, authority, cost-risk, or irreversible decisions.
- Report material scope/risk reversals, workflow-wide blockers, delivery-readiness changes, and completion.
- Perform only authorized delivery; never auto-merge/deploy without separate authority.
- Final report: outcome/artifact or PR, acceptance evidence, changed scope, calibrated claims/limits, cost variance, and deferred optional work. Omit worker history unless asked.
- Clear owned leases, stop owned dashboard processes, retain evidence, and archive completed artifacts when safe.
