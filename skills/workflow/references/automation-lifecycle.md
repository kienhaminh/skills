# Automation lifecycle

The workflow graph is provider-neutral. The caller owns Goal/loop/manual lifecycle, authority, scheduling, and user-visible status.

## Explicit workflow identity

- **Create:** `$workflow <objective>` derives an unused kebab-case ID, creates `.codex/workflows/<id>/`, and returns the ID.
- **Activate/resume:** caller must supply exact `workflow_id`; never infer it from chat, branch, Goal, or directory proximity.
- Resolve with `python3 <skill-dir>/scripts/workflow_state.py resolve .codex/workflows --workflow-id <id>`.
- `graph.json` stores only `workflow_id`; caller/provider IDs stay in runtime state.

## Artifact layout

```text
.codex/workflows/<id>/
  graph.json
  runtime.json
  memory/state.json
  memory/events.jsonl
  memory/capsules/
  prototype/
  evidence/
  dashboard/
```

`runtime.json` may record caller type/ID, invocation, lease owner/heartbeat, authority, dashboard PID/port, worktrees, and timestamps. Shared memory stores learned cross-node state through coordinator-applied deltas. Do not embed credentials, prompt transcripts, or provider-specific fields in graph/runtime/memory.

## State machine

```text
draft -> ready -> active -> waiting -> active -> complete
                    \-> blocked
```

- `ready`: graph validates executable, including prototype gate.
- `active`: at least one live owned node or integration action.
- `waiting`: only user/approval/external dependencies remain.
- `blocked`: required coverage cannot progress under current authority/environment.
- `complete`: complete-phase validation passes; caller delivery may still be pending.

Acquire one workflow lease before mutation. Refresh heartbeat during work; release it on clean stop. Use atomic state writes. A second invocation observes or resumes; it never silently forks the same graph.

## Authority intersection

Effective authority = user request ∩ caller policy ∩ repository policy. Local edits/tests are allowed only when the request authorizes implementation. Commit, push, PR, merge, deploy, destructive actions, credentials, and objective expansion require explicit authority at the appropriate level. Optional ready-PR delivery does not imply merge/deploy.

## Resume + recovery

1. Resolve exact ID and lease.
2. Reconcile runtime claims against live agents, sessions, worktrees, processes, and artifacts.
3. For stale modifying work, inspect the diff before reassigning or cleaning anything.
4. Accept completed work only after owned diff and evidence checks.
5. Retry once after shrinking/clarifying the node contract; otherwise escalate the classified blocker.
6. Revalidate and dispatch only the new ready frontier.

Never erase a failed branch from requirement coverage.

## Outcome-only communication

Keep routine scheduling, polling, routing, and retries internal. Ask only for material intent, prototype/baseline, authority, cost-risk, or irreversible decisions. Report material scope/risk reversals, workflow-wide blockers, delivery-readiness changes, and completion.

On completion: clear owned leases, stop owned dashboard processes, retain evidence, and archive under `.codex/workflows/completed/<id>/` only after callers no longer need the active path.
