# Integrity — Proof-Carrying Work

Treat worker output and worker-authored evidence as untrusted until reproduced by the coordinator-owned runner and independently challenged.

## Design by Contract + Oracle Lock

Adapt `integrity/verification-plan.json` before broad implementation, then lock it:

```bash
python3 <skill-dir>/scripts/evidence_runner.py lock <workflow-dir> --repo-root <repo>
python3 <skill-dir>/scripts/evidence_runner.py validate <workflow-dir> --phase active --repo-root <repo>
```

The plan maps every requirement to a critical executable check, explicit watched state, negative/challenge classes, and a verify node. Locking pins plan, runner, and semantic graph digests. Never weaken a locked oracle; a material change requires a new workflow baseline or user-confirmed supersession outside this script.

## Reproducible Evidence

Run checks only through the pinned runner:

```bash
python3 <skill-dir>/scripts/evidence_runner.py run <workflow-dir> --check <id> --repo-root <repo>
```

The runner uses argv without a shell, captures exit/timing/log digests, hashes watched files before/after, and writes a digest-bound attestation. Changed watched state, stale plan/graph/runner digest, missing log, wrong exit, or an incomplete fabricated envelope fails validation. A root coordinator can still forge local files; high-risk work therefore requires an external gate.

## Separation of Duties + Two-Key Completion

Producer completion is not acceptance. A fresh verify node consumes runner attestations, performs the plan's challenge classes, and returns a bounded verification proposal. The coordinator validates exact requirement/evidence binding, materializes the review input, records it, and alone updates graph claims:

```bash
python3 <skill-dir>/scripts/evidence_runner.py record-review <workflow-dir> <review.json> --repo-root <repo>
```

Verifier nodes must be disjoint from producer nodes. Producer shared-memory entries are capped below `verified`; only verify nodes may reference runner attestations as verified memory.

## Non-compensatory completion

```bash
python3 <skill-dir>/scripts/evidence_runner.py validate <workflow-dir> --phase complete --repo-root <repo>
```

Completion requires every critical check to pass against current watched state, every required challenge class to have a passing attestation, the verifier quorum to pass, and every verified graph claim to cite a matching runner attestation. One critical failure blocks completion regardless of aggregate score.

Risk tiers: low requires one challenge class and verifier; medium requires two classes and verifier; high requires three classes, mutation testing, two verifiers, and an external gate. The verifier must inspect the external gate's provider provenance; the local digest only pins its exported copy. Local integrity is a guardrail, not a cryptographic boundary against a root coordinator that can rewrite the trusted runner; use protected external CI for high-risk work.
