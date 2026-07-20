# Authorized delivery — Ship + Transactional Outbox

Use the current project-local `ship` skill as the repository contract. Preserve its **Gate → Record → Commit → Publish** order; Graphflow supplies isolation, durable state, and idempotent recovery.

## Graph preparation

- Model Ship as `Gate -> Record -> release integration -> independent verification -> broker`. Gate runs the repository-applicable type-check, scoped tests, `/verify`, and `/code-review` checks from the current Ship playbook. A red Gate blocks Record and Publish.
- If an active plan drove the work, a bounded graph node applies Ship **Record**: prepend the factual `## Outcome (YYYY-MM-DD)`, move active → completed, remove resolved tech debt, and add a lesson only when genuinely earned.
- Rerun affected release checks during final integration and independent verification after Record so the verified tree includes both the implementation and complete paper trail.
- Internal worktree checkpoint commits are recovery objects, not the public Ship commit.

Configure `runtime.json.delivery`, never `graph.json`, with:

- adapter `ship-v1`, canonical remote `origin`, base `master`, and a distinct head branch;
- Record mode (`no_plan` with a concrete reason, or active/completed plan paths);
- conventional English commit subject/body;
- PR title/body using `## Goal`, `## What changed`, and `## Verification`;
- exact capabilities: `commit`, `push`, `pull_request`, `network`, `credentials`.

Do not store credential values.

## Coordinator broker

After all completion gates pass, `delivery_broker.py`:

1. proves every verifier inspected the same clean integration checkpoint;
2. reruns complete proof validation, verifies Ship Record, and freezes `runtime/delivery/manifest.json` with graph/verification digests, base SHA, verified SHA/tree, branch, commit, and PR surfaces;
3. creates one digest-bound approval showing the exact tree, branch, base, commit subject/body, and PR title/body;
4. after approval, creates a deterministic squash commit whose tree equals the verified tree and whose parent equals the pinned base;
5. requires the remote base still equal the pinned base and refuses force-push over a different head;
6. atomically pins the unchanged base ref while pushing the exact release SHA, then verifies both refs with `git ls-remote`;
7. creates, reuses, or updates the matching PR through `gh`, then writes `runtime/delivery/proof.json`;
8. revokes the broker grant and completes the workflow.

The broker never switches or rewrites the user's primary checkout. Retain the verified integration/verifier worktrees as reproducible evidence while the PR is open; clean them only during explicit workflow archival or after another durable checkout can reproduce the release proof.

Use:

```bash
python3 <skill-dir>/scripts/delivery_broker.py inspect <workflow-dir>
python3 <skill-dir>/scripts/delivery_broker.py advance <workflow-dir> --repo-root <repo>
```

The normal `run_workflow.py` loop calls `advance` automatically after local completion gates.

## Fail closed + recovery

- Pending/rejected approval performs no commit, push, or PR mutation.
- Fabricated, stale, or post-approval verification evidence blocks publication; valid evidence drift supersedes the old request and creates a fresh manifest-bound approval.
- Remote base drift requires rebase → reintegration → fresh verification → a new manifest and approval.
- An existing remote head at another SHA blocks; never force-push automatically.
- Auth/network/provider errors become `waiting_external`; resume retries only Publish, not implementation.
- A matching remote SHA or PR is reused; repeated execution is idempotent.
- Merge and deploy are outside `ship-v1` and always require separate policy, capability, and implementation.
