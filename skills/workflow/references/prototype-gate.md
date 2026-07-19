# Prototype Gate — intent baseline

Use the cheapest artifact that can falsify a wrong interpretation before broad execution.

| Uncertainty | Prototype | Default |
| --- | --- | --- |
| Layout, copy, flow | Standalone HTML/wireframe | Disposable |
| Existing routing/auth/data | Dev-only isolated worktree | Promotable after hardening |
| API/backend contract | Examples, mock handler, failure table | Specification |
| Bug/refactor | Characterization test or minimal reproduction | Promotable test |
| Data/automation | Before-after sample, dry-run, rollback/trace | Evidence |
| Research/document | Outline plus representative section/table | Baseline |

Disposable artifacts live under `.codex/workflows/<id>/prototype/`; promotable code uses an isolated worktree, never the shared modifying checkout.

## Manifest + graph lock

Write `prototype/manifest.json` with: schema/workflow ID, canonical method, artifact, promotable flag, fidelity, mocked boundaries, `not_proven`, status, approval, and digest. Example: [template manifest](../assets/workflow-template/prototype/manifest.json).

Mirror the lock in root `intent_baseline`:

- **Required:** `required: true`; a normalized manifest path; one prototyping node; `approved` plus `sha256:<64 hex>` and `approval: user|deterministic` before executable phase.
- **Exempt:** only deterministic mechanical work with no unresolved intent choice; use `required: false`, `not_required`, null manifest/digest/approval, and a concrete reason.
- Every implementation/integration node must descend from the completed prototype node when required.

`deterministic` approval means the prototype has a machine oracle, such as a characterization test or validated dry-run. It never means agent self-approval of subjective intent.

## Drift control

- Require user approval for user-visible, subjective, public-contract, data-changing, or materially ambiguous behavior.
- Hash the reviewed artifact and freeze it. A baseline change requires a concise delta, impact, alternative, and renewed approval.
- At completion compare integrated behavior, non-goals, mocked boundaries, and `not_proven` against the baseline.
- A mock/static prototype proves intent only; it is never product or runtime evidence.
