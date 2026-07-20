# Primary checkout guard — Zero Trust + TOCTOU + Fail-Closed

The primary checkout is a pinned integration input, not a worker workspace. Every modifying node writes only in its registered Graphflow-owned worktree. A declared node scope authorizes paths inside that worktree; it never authorizes mutation of the primary checkout.

## Baseline

Apply **Snapshot Isolation + Content Addressing** before the first dispatch:

```bash
python3 <skill-dir>/scripts/checkout_guard.py --repo-root <repo> init <workflow-dir>
```

The local baseline records branch, HEAD, semantic Git controls/index, and SHA-256 state for every tracked change or non-ignored untracked path already present. `runtime.json` seals the baseline artifact digest; mismatch fails closed instead of silently rebaselining. Existing user dirt is preserved as baseline; contents, credentials, ignored files, and workflow control-plane files are not copied into events or dashboard projections. A legacy workflow with durable results but no baseline must be inspected/reframed before resume.

Graphflow runtime/control-plane paths are excluded from the product-checkout snapshot and protected independently by `node_runner.py`. The graph digest and declared write owners are bound for attribution only. A change is still drift when its path has a declared owner because the owner must work in its isolated worktree.

## Monitor + decision

Apply **TOCTOU Defense + Event Sourcing** before reconciliation, before dispatch, after every parallel frontier exits, and before completion/Ship:

```bash
python3 <skill-dir>/scripts/checkout_guard.py --repo-root <repo> check <workflow-dir>
python3 <skill-dir>/scripts/checkout_guard.py inspect <workflow-dir>
```

- Exact match: continue and journal only material state changes.
- Checkout drift: preserve durable worker results, create one workflow-scoped digest-bound request, stop dispatch/consume/Ship, and show affected paths plus declared owners.
- Exact approved digest: adopt that observed state once as the new baseline, consume the request, and resume.
- State or semantic graph changes after approval: supersede it and require a new exact decision.
- Rejection: remain blocked until the checkout is externally restored/reconciled; returning exactly to baseline clears the guard without adoption.

Never auto-restore, stash, reset, delete, commit, or rebaseline user state. A clean `git status` is insufficient: branch, HEAD, staged index, Git config/info/hooks, and dirty-path content are part of the decision surface. The logical index digest excludes volatile stat-cache bytes so a content-preserving `git restore` can return to baseline.

## Parallel frontier

Apply **Bulkhead + Two-Phase Handoff**. Workers run concurrently only in disjoint registered worktrees. The runner waits for the whole frontier, then checks the primary checkout before consuming any result. If another task or escaped executor changed it, all result envelopes remain durable and unaccepted; after confirmed reconciliation, normal scope checks, coordinator checkpoints, integration, independent verification, and Ship resume idempotently.

The read-only dashboard projection is `/checkout.json`. It exposes status, counts, control-change flags, paths, change classes, and declared owners—never repository roots, file contents, raw Git metadata, confirmation answers, or credentials.
