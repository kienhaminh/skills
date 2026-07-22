# Subagent routing — Token Economy + Critical Path

The persistent runner owns dispatch; the coordinator owns graph mutation, acceptance, integration, authority, and delivery. Workers own exactly one node contract; they never expand scope or edit graph state. Compile deterministic work to `command` executors and model work to `agent` executors. In-chat subagents are an optional provider adapter, not a liveness mechanism.

## Cheapest sufficient model

| Node shape | Default model/effort | Escalate when |
| --- | --- | --- |
| Inventory, profile, deterministic checks, bounded docs | small / low | conflicting sources or judgment changes outcome |
| Scoped implementation/test/spec with local oracle | small / medium | one corrected retry shows reasoning failure |
| Cross-boundary contract, integration, ambiguous diagnosis | frontier / medium-high | irreversible/high-stakes uncertainty remains |
| Graph design, pivotal intent, final synthesis | coordinator frontier | n/a |

Provider model names live only in the agent adapter map. Graph contracts describe model class, capability, budget, and routing reason—not a caller or provider dependency. Freeze the selected model class in the executor spec and digest after the cost choice.

## Routing score

Use the least costly route satisfying:

```text
risk = ambiguity × blast_radius × reversibility^-1 × oracle_weakness
```

Critical-path or uncertainty-reducing nodes win ties. Parallelize only independent nodes with disjoint ownership. Do not parallelize a tiny graph merely to occupy slots.

## Context budget

For agent executor prompts, including fresh in-chat adapters, pass only:

1. method names and one task-specific application;
2. node outcome/non-goals, scopes, acceptance, budget, return schema;
3. required trust-order files and selected complete skill paths;
4. named dependency artifacts plus short verified summaries;
5. one bounded shared-memory capsule generated for the node.

Never pass main chat, full shared state/event log, unrelated branches, worker transcripts, broad doc trees, dashboard data, or another worker's reasoning. Persist outcomes/evidence references, not chain-of-thought. Workers return the standard result envelope with a proposed `memory_delta`; only the runner/coordinator applies it after validation.

## Isolation

- Read-only workers may share checkout.
- Concurrent modifiers use separate worktrees with disjoint write scopes.
- The standalone runner serializes modifiers whose registered workspaces resolve to the same path; parallel modification requires distinct coordinator-provisioned worktree refs.
- One integration owner controls shared convergence paths.
- A verifier is fresh, read-only where possible, receives the locked plan plus runner attestations but no producer reasoning, and is never reused from a producer role in the same graph.

## Retry ladder

Classify failure: `contract`, `context`, `reasoning`, `environment`, `authority`, or `external`.

1. Contract/context: shrink or clarify once; keep same model.
2. Reasoning: after one corrected attempt, escalate one tier with only contract, artifacts, failure evidence, and rejected approach.
3. Environment/authority/external: do not spend a stronger model; repair environment, wait, or ask for authority.

Maximum is one corrected retry (`max_attempts: 2`). Repeated failure becomes a blocker or graph redesign, not recursive delegation.

## Acceptance return

Workers return only the standard result envelope: outcome; files/artifacts; evidence references; memory delta; blockers, digest-bound request, or a structural decomposition proposal; usage. A verify node may additionally return the bounded verification proposal defined by the result schema. A worker never mutates the graph. The runner reproduces acceptance checks, and the coordinator independently validates decomposition or verification proposals before marking completion or revising the graph.
