# Runtime structural decomposition

Apply **Refinement Calculus + MECE + Well-Founded Induction + Proof-Carrying Work**. A running agent may propose smaller child nodes when its bounded work is structurally too large, but it never edits the graph or changes the contract itself.

## Decision boundary

Return `status: decompose` only for `complexity`, `context`, or a newly exposed `hidden_dependency` when all of these remain invariant:

- objective, required acceptance, approved prototype, non-goals, authority, and locked verification checks;
- the parent's total write, artifact, and decision ownership;
- original inputs and outputs; one terminal child preserves every original output exactly;
- total child token budgets plus one coordination token do not exceed the parent budget.

Use `waiting_user`/`waiting_approval` with `resolution_mode: rebase` instead when the uncertainty affects intent, acceptance, scope expansion, authority, prototype, oracle, cost-risk choice, or an irreversible action. Automatic decomposition is limited to `agent` `execute` nodes; command, integration, and verification redesigns require rebase.

## Proposal contract

The result's `decomposition` object declares:

- `contract_change: structural` and one controlled `reason_class`;
- a named integer complexity measure with every child strictly below the parent; a recursively decomposed child must reuse its persisted name and exact inherited parent bound;
- at least two uniquely keyed children and one `terminal_child`;
- each child's operations, methods, derived skills, dependencies, scope, inputs/outputs, acceptance checks, and token budget.

Apply **Ranking Function**: persist each assigned child value as normative `decomposition_bound`; a later split must reuse its name and use that exact value as `measure.parent`. Do not reset or rename the measure. Apply **Conservation Law**: children exactly partition parent write/artifact/decision scope, preserve every forbidden boundary, and cannot expand readable roots. Support children must be ancestors of the terminal child; the terminal consumes all support outputs and preserves the parent's acceptance list exactly. Apply **Closed World Assumption** to the oracle: every child uses only existing parent `acceptance_checks`, every child has at least one, and the union equals the parent check set exactly—never invent a child-only check. A `decompose` envelope carries no outputs, evidence, memory delta, or request.

## Coordinator broker

`run_workflow.py` sends a valid proposal to `decomposition_broker.py`. The broker applies **Two-Phase Commit + Independent Verification**:

1. build a candidate revision outside the live workflow;
2. replace the parent with an `expanded` bookkeeping node and materialize its children;
3. preserve the parent's original dependencies on every child and redirect external dependents to the terminal child;
4. rebind the parent's registered workspace to the terminal child and allocate separate worktrees to support modifiers;
5. reuse a valid **Content-Addressable Cache** entry keyed by candidate graph, proposal, verification-plan digest, reviewer prompt/contract, policy/model/effort; otherwise run one fresh low-cost artifact-only challenger for misread intent, hidden dependency, and oracle gap;
6. re-lock question review and verification oracles, bind shared memory, and validate the candidate as executable;
7. commit the revision with backup, Merkle manifest, proposal, review, proof, and `journal.json` under `runtime/decompositions/<revision>/`.

Apply **Write-Ahead Logging + Merkle Tree** with `preparing -> prepared -> committing -> committed -> finalized`. Write and fsync the journal before live mutation. Hash every present core file and integrity-review file into `backup-manifest.json`; verify exact coverage, leaf bytes, and root digest before live commit or rollback. On resume, a `committing` revision rolls back from its bounded backup and archives the durable result; a valid `committed` revision rolls runtime forward idempotently, then becomes `finalized`. If committed-state validation or finalization fails, restore the verified backup once and block instead of retrying a poisoned new state. Validate journal IDs, paths, cache bindings, manifests, and digests before recovery mutation.

Apply **Fail-Safe Defaults** to a valid reviewer `open` outcome: keep the live graph unchanged, cache the review, set `runtime.decomposition.status: waiting_rebase`, and emit exactly one canonical-digest-bound `resolution_mode: rebase` request covering only the node and its descendants. The scheduler continues unrelated ready branches. Invalid reviewer output or a broken structural invariant remains `blocked`; workers cannot write control-plane files, forge review/cache artifacts, or self-approve the rewrite.

## Parallel progress and recovery

Apply **Bulkhead + Critical Path** after revision. Newly ready children use the normal frontier selector: disjoint registered worktrees may run in parallel; overlapping ownership, a shared workspace, or a dependency serializes them. Unrelated ready branches continue.

The parent result remains durable but is no longer executable after replacement. On crash, only `active` executable nodes reconcile results. Fault-injection evals send real `SIGKILL` at `prepared`, first-child copy, live validation, and `committed`; a fresh broker must recover to the exact old or new digest. The proof binds old/new graph, proposal/review/cache, child IDs, terminal child, budget conservation, and measure decrease. Dashboard status comes from `runtime.decomposition`; graph state remains normative.
