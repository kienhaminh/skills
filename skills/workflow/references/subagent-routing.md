# Subagent routing — Token Economy + Critical Path

The coordinator owns graph mutation, dispatch, acceptance, integration, authority, and delivery. Workers own exactly one node contract; they never expand scope or edit graph state.

## Cheapest sufficient model

| Node shape | Default model/effort | Escalate when |
| --- | --- | --- |
| Inventory, profile, deterministic checks, bounded docs | small / low | conflicting sources or judgment changes outcome |
| Scoped implementation/test/spec with local oracle | small / medium | one corrected retry shows reasoning failure |
| Cross-boundary contract, integration, ambiguous diagnosis | frontier / medium-high | irreversible/high-stakes uncertainty remains |
| Graph design, pivotal intent, final synthesis | coordinator frontier | n/a |

Model names are caller-specific runtime metadata. Graph contracts describe capability, budget, and routing reason—not a provider dependency.

## Routing score

Use the least costly route satisfying:

```text
risk = ambiguity × blast_radius × reversibility^-1 × oracle_weakness
```

Critical-path or uncertainty-reducing nodes win ties. Parallelize only independent nodes with disjoint ownership. Do not parallelize a tiny graph merely to occupy slots.

## Context budget

With `fork_turns: "none"` where supported, pass only:

1. method names and one task-specific application;
2. node outcome/non-goals, scopes, acceptance, budget, return schema;
3. required trust-order files and selected complete skill paths;
4. named dependency artifacts plus short verified summaries;
5. one bounded shared-memory capsule generated for the node.

Never pass main chat, full shared state/event log, unrelated branches, worker transcripts, broad doc trees, dashboard data, or another worker's reasoning. Persist outcomes/evidence references, not chain-of-thought. Workers return a proposed `memory_delta`; only the coordinator applies it.

## Isolation

- Read-only workers may share checkout.
- Concurrent modifiers use separate worktrees with disjoint write scopes.
- One integration owner controls shared convergence paths.
- A verifier is fresh, read-only where possible, and receives no producer reasoning.

## Retry ladder

Classify failure: `contract`, `context`, `reasoning`, `environment`, `authority`, or `external`.

1. Contract/context: shrink or clarify once; keep same model.
2. Reasoning: after one corrected attempt, escalate one tier with only contract, artifacts, failure evidence, and rejected approach.
3. Environment/authority/external: do not spend a stronger model; repair environment, wait, or ask for authority.

Maximum is one corrected retry (`max_attempts: 2`). Repeated failure becomes a blocker or graph redesign, not recursive delegation.

## Acceptance return

Workers return only: outcome; files/artifacts; exact checks/evidence; owned decisions; blockers/scope request; actual token estimate. Coordinator verifies the owned diff and acceptance before marking complete.
