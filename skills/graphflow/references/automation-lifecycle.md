# Automation lifecycle

The graph schema, scheduler, and caller lifecycle are coding-tool neutral. Graphflow stores workflows
under `.graphflow/`; agent execution is available only through an explicit digest-locked adapter.
Chat tasks, loops, IDEs, and manual callers remain optional invocation and observation adapters.

## Explicit workflow identity

- **Create:** `$graphflow <objective>` derives an unused kebab-case ID, creates `.graphflow/workflows/<id>/`, and returns the ID.
- **Activate/resume:** caller must supply exact `workflow_id`; never infer it from chat, branch, caller session, or directory proximity.
- Resolve with `python3 <skill-dir>/scripts/workflow_state.py resolve .graphflow/workflows --workflow-id <id>`.
- `graph.json` stores only `workflow_id`; caller/provider IDs stay in runtime state and never become liveness dependencies.

## Artifact layout

```text
.graphflow/workflows/<id>/
  graph.json
  runtime.json
  runtime/events.jsonl
  runtime/lease.json
  runtime/requests/
  runtime/results/
  runtime/workspaces.json
  runtime/checkout-baseline.json
  runtime/checkout-status.json
  runtime/checkout-events.jsonl
  runtime/progress/<node-id>.json
  runtime/decompositions/<revision>/proposal.json
  runtime/decompositions/<revision>/review.json
  runtime/decompositions/<revision>/proof.json
  runtime/decompositions/<revision>/journal.json
  runtime/decompositions/<revision>/backup-manifest.json
  runtime/decompositions/cache/<content-digest>.json
  runtime/delivery/manifest.json
  runtime/delivery/proof.json
  runtime/delivery/events.jsonl
  nodes/<node-id>/executor.json
  nodes/<node-id>/prompt.md
  nodes/node-result.schema.json
  memory/state.json
  memory/events.jsonl
  memory/capsules/
  integrity/verification-plan.json
  integrity/lock.json
  integrity/reviews/
  prototype/
  evidence/attestations/
  dashboard/
```

`runtime.json` may record optional caller binding, invocation, authority, dashboard PID/port, worktrees, and timestamps. Lease, events, requests, and results use the dedicated runtime paths above. Shared memory stores learned cross-node state through coordinator-applied deltas. Do not embed credentials, prompt transcripts, or environment values.

## State machine

```text
draft -> ready -> active -> waiting -> active -> complete
                    \-> blocked
```

- `ready`: graph validates executable, including prototype and oracle-lock gates.
- `active`: at least one live owned node or integration action.
- `waiting`: only user/approval/external dependencies remain. After local graph completion, Ship approval/external waits live only in `runtime.scheduler` and `runtime.delivery`; keep normative `graph.lifecycle=complete` so its locked evidence contract does not drift.
- `blocked`: required coverage cannot progress under current authority/environment.
- `complete`: complete-phase validation passes and required Ship delivery has a current remote/PR proof; unrequested delivery remains `not_required`.

Acquire one workflow lease before mutation. Refresh heartbeat during work; release it on clean stop or waiting. Use atomic writes and idempotency keys. A second invocation observes or resumes; it never silently forks the same graph.

## Authority intersection

Effective authority = user request ∩ caller policy ∩ repository policy. Local edits/tests are allowed only when the request authorizes implementation. Commit, push, PR, merge, deploy, destructive actions, credentials, and objective expansion require explicit authority at the appropriate level. Optional ready-PR delivery does not imply merge/deploy.

## Resume + recovery

1. Resolve exact ID and acquire the lease.
2. Under the workflow lease, recover any decomposition write-ahead journal; then validate executor digests and apply [Primary checkout guard](checkout-guard.md) before reconciling durable results, sessions, worktrees, processes, and artifacts.
3. For stale modifying work, inspect the diff before reassigning or cleaning anything.
4. Accept completed work only after owned diff, evidence checks, and a coordinator-written terminal progress snapshot.
5. Retry once after shrinking/clarifying the node contract; otherwise escalate the classified blocker.
6. Consume only digest-matching confirmations.
7. Revalidate and dispatch only the new ready frontier through `run_workflow.py`.

A structurally oversized agent node may propose [runtime decomposition](runtime-decomposition.md). The coordinator uses a candidate revision, content-addressed independent challenge, and Merkle-bound recovery. Semantic ambiguity creates one branch-scoped digest-bound rebase request; unrelated ready branches continue under normal workspace bulkheads.

Apply [question triage](question-triage.md) and lock a fresh independent challenge before `ready`. A waiting node blocks only itself and descendants; continue independent ready nodes until no runnable frontier remains. Migrate v1/v2 workflows to a sibling v3 artifact with `migrate_workflow.py`; never reinterpret or overwrite the source in place.

Never erase a failed branch from requirement coverage.

## Outcome-only communication

Keep routine scheduling, polling, routing, and retries internal. Ask only for material intent, prototype/baseline, authority, cost-risk, or irreversible decisions. Report material scope/risk reversals, workflow-wide blockers, delivery-readiness changes, and completion.

Caller independence is a release gate: the same workflow must reach an honest terminal/waiting state from `run_workflow.py` with no chat, IDE, or loop binding. The lifecycle eval must invoke the real runner through recursive decomposition, parallel worktrees, integration, verification proposal, approval wait/resume, and Ship proof; directly marking nodes complete is not lifecycle evidence. On completion, clear owned leases, stop owned dashboard processes, retain evidence, and archive only after observers no longer need the active path.
