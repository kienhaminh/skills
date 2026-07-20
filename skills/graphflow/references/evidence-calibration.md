# Evidence calibration — anti-overconfidence contract

## Evidence Hierarchy + Bayesian Updating

Prefer evidence matching the claim: end-to-end observation, integration test, focused test, static check, code inspection, producer assertion. Update confidence only when evidence changes likelihood.

| State | Confidence cap | Meaning |
| --- | --- | --- |
| `verified` | `high` or `medium` | Direct check covers the exact integrated claim |
| `observed` | `medium` or `low` | Direct check covers a narrower case |
| `inferred` | `low` | Only indirect support |
| `unverified` | `none` | Missing, blocked, or contradictory check |

Producer completion, confidence, test existence, code inspection, and manually written evidence JSON are not verification. Never turn unavailable evidence into a pass.

## Machine record

The verifier proposes explicit evidence paths; the coordinator validates and writes root `verification.claims`:

```json
{
  "id": "C-R1",
  "requirement_id": "R1",
  "statement": "Exact claim",
  "state": "verified",
  "confidence": "high",
  "evidence": [{"check": "CHK-R1-CONTRACT", "artifact": "evidence/attestations/CHK-R1-CONTRACT.json"}],
  "limitations": []
}
```

- A claim with `requirement_id` is primary. Complete phase requires exactly one primary, `verified` claim per requirement.
- `verified` requires a current passing `workflow-evidence-runner-v1` attestation owned by a verify node. `observed` still requires direct scoped evidence.
- Extra claims use `requirement_id: null`. Non-verified extras force `verification.outcome: complete_with_limits` but do not invalidate completed required outcomes.
- If a required claim cannot be verified, keep the graph blocked; do not run complete phase.

## Popperian Falsification

Give a fresh verifier requirements, approved baseline, locked plan, integrated artifacts, and known limits—never producer reasoning. Seek counterexamples through negative, boundary, differential, metamorphic, mutation, concurrency, or permission checks as applicable. The coordinator records an accepted proposal through `evidence_runner.py record-review`; prose cannot substitute for an attestation.

Report calibrated language: “verified by…”, “observed for…”, “inferred because…”, or “not verified; limit…”.
