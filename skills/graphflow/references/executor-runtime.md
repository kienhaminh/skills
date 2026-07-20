# Executor runtime

Apply **Dependency Inversion + Design by Contract + Event Sourcing**. Graphflow schedules durable node executors; Goal is an optional adapter that may observe, notify, or invoke the same resume command.

## Artifact contract

```text
<workflow>/
  graph.json
  runtime.json
  runtime/events.jsonl
  runtime/lease.json
  runtime/requests/<request-id>.json
  runtime/results/<node-id>.json
  runtime/workspaces.json
  runtime/checkout-baseline.json
  runtime/checkout-status.json
  runtime/progress/<node-id>.json
  runtime/decompositions/<revision>/{journal,proposal,review,proof}.json
  nodes/<node-id>/executor.json
  nodes/<node-id>/prompt.md          # agent only
  nodes/node-result.schema.json
```

`graph.json` declares dependencies, ownership, executor type/spec/digest, and result path. Executor specs contain provider/runtime choices. Runtime files contain leases, processes, requests, results, and optional Goal bindings. Never put credentials, environment values, transcripts, or chain-of-thought in any artifact.

## Executor spec

Common fields: `schema_version: 2`, matching `node_id`, `type`, exact `workspace: {mode, ref, subdir}`, `timeout_seconds`, `idempotency_key`, `result_schema`, `acceptance_checks`, `requires_authority`, optional environment-variable names in `env_allow`, and `resources` containing digests for the result schema plus every local prompt/script. `mode` is `primary`, `worktree`, `integration`, or `verifier`; `subdir` is normalized and relative. Lock the exact spec bytes with SHA-256 in `graph.json`; this transitively locks its resources.

`runtime.json.authority` defaults every capability to false. Record only explicitly granted `local_write`, `commit`, `push`, `pull_request`, `merge`, `deploy`, `destructive`, `network`, or `credentials` capabilities. Before dispatch, the runner creates a digest-bound request for missing declared capabilities; approval creates a node-scoped `authority_grants` entry, and terminal handoff revokes it. The node runner rejects missing or undeclared grants. Commit/push/PR remain separate; merge/deploy is never implied.

If delivery is required, model Ship Gate before its bounded Record node, then rerun affected release checks through final verification before using coordinator-owned `delivery_broker.py`. Do not model commit/push/PR as worker executors: the broker binds one approval to the verified tree and handles their distinct recovery/idempotency states without exposing credentials. Never encode secrets in argv, resources, runtime, or events.

- `command`: declare non-empty `argv`; the runner uses no shell and creates the result envelope from exit state.
- `agent`: declare `prompt`, optional provider model/effort, and `sandbox` (`read-only` or `workspace-write`). The local adapter invokes `codex exec` non-interactively with stdin, JSON events, and the output schema. It never uses `danger-full-access` or bypass flags.

Generate prompts from the compact worker contract and bounded memory capsule. Include selected skill paths, named inputs, scopes, acceptance, authority, budget, and result schema. Never include main chat history or hidden reasoning.

## Acceptance and anti-cheating

The executor may report `succeeded`, but the runner accepts it only when:

1. the envelope matches the standard schema and workflow/node/attempt identity;
2. declared outputs exist inside owned scopes and any supplied digest matches;
3. every `acceptance_checks` ID exists in the locked verification plan and passes through `evidence_runner.py` against current watched state;
4. memory deltas and any verifier proposal pass their independent validators.

A producer cannot mark itself verified. Failed critical checks are non-compensatory. Empty acceptance checks are allowed only for already-complete expansion/prototype bookkeeping; executable pending work must have at least one coordinator-run check.

Before raw execution, inventory protected control-plane roots (`nodes`, integrity, memory, prototype, dashboard, attestations, requests, decomposition, delivery, scope), reject symlinks, and snapshot every existing file plus the current node's progress snapshot. After raw execution, quarantine newly forged paths, restore changed/deleted bytes, fail the node, then run no acceptance checks. Parallel peer progress is intentionally outside the frozen directory inventory; it cannot complete a node because completion also requires that node's coordinator-written terminal progress snapshot.

The verifier result may add one `verification` proposal only on `succeeded`. It carries outcome, challenge classes, claims, and limitations, but it is not control-plane authority. `run_workflow.py` accepts it only from the configured detached verifier, requires every current critical attestation, exact requirement coverage and statement binding, locked evidence paths, calibrated confidence, and challenge-policy coverage; it then records the review and atomically writes the candidate graph.

## Persistent scheduler

`run_workflow.py` owns one atomic lease and repeatedly:

1. validate executable graph and locked executor digests;
2. enforce the [Primary checkout guard](checkout-guard.md), then reconcile durable results and stale processes;
3. consume digest-bound confirmation responses;
4. select up to `max_parallel` ready nodes with disjoint ownership; resolve registered workspaces, serialize modifiers sharing a path, and provision distinct worktrees for parallel modifiers;
5. run `node_runner.py` processes and append events;
6. recheck the primary checkout before consuming the completed frontier;
7. validate result envelopes and acceptance attestations;
8. broker any structural `decompose` proposal through a candidate revision, independent challenge, oracle relock, and executable validation;
9. apply transitions and memory deltas atomically;
10. continue until `complete`, `blocked`, or a waiting state.

Use `--once` for one frontier and `--dry-run` for projection. A crash leaves the event log and result files; resume reconciles them before dispatch and must not duplicate a matching idempotency key.

## Decomposition broker

`decompose` is valid only for an agent `execute` node and must carry only a structural proposal satisfying [runtime structural decomposition](runtime-decomposition.md); its other result channels stay empty/null. The worker proposes; `decomposition_broker.py` alone validates, uses a content-addressed independent challenge, rebinds workspaces/memory, relocks the oracle, and journals a Merkle-backed revision. `run_workflow.py` recovers pending journals under the workflow lease before graph validation or result reconciliation. A valid pivotal review leaves the original graph intact and creates one branch-scoped semantic rebase request; malformed review or invariant failure blocks the revision.

## Confirmation broker

An agent that passes [Question Triage](question-triage.md) returns a waiting result with a path-safe request ID, concise question, alternatives, risks, triage metadata, and the canonical SHA-256 of `{question, alternatives, risks, triage}`. `resolution_mode` and `request_graph_digest` prevent stale approval reuse. A branch request releases only that branch; a workflow request pauses dispatch. Semantic answers require a validated rebase; non-semantic answers require the graph digest to remain unchanged. Record the response with:

```bash
python3 <skill-dir>/scripts/confirm_workflow.py <workflow-dir> \
  --request-id <id> --digest <sha256:...> --decision approved --answer <text>
```

The next run supplies only that response to the same executor. A changed request digest invalidates the response.

## Optional Goal adapter

Goal may store a provider binding in `runtime.json`, show material events, or invoke the same resume command. It must not own graph state, dispatch nodes, synthesize confirmations, or be required for liveness. Test the core lifecycle with no Goal present.
