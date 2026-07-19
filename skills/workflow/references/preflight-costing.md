# Preflight costing — only when material

Use this reference only for a hard budget, user-requested options, or material runtime/disk/money/risk uncertainty. Otherwise choose the cheapest sufficient route internally.

## Sanitized two-layer profile

Run one low-cost agent to inspect machine/repo capabilities. Persist:

- global sanitized profile: `~/.codex/workflow/machine-profile.json`;
- repo overlay: `.codex/workflow/repo-profile.json`.

Use `python3 <skill-dir>/scripts/profile_environment.py --global-output <path> --repo-output <path>`. Refresh only when stale or environment drift matters.

Allowed: OS/architecture, CPU/RAM class, free disk, tool versions, container/browser availability, repo size/languages/test commands, worktree support. Exclude environment values, credentials, process arguments, serials, arbitrary user files, and unrelated paths.

## Three options

Return `economy`, `balanced`, and `deep`. Each records:

```json
{
  "id": "balanced",
  "models": [{"class": "small", "nodes": 4}, {"class": "frontier", "nodes": 1}],
  "estimated_tokens": 12000,
  "wall_time_minutes": [20, 40],
  "disk_mb": [100, 600],
  "money": null,
  "currency": null,
  "confidence": "medium",
  "assumptions": ["focused tests available"],
  "risks": ["integration may require one escalation"],
  "mitigations": ["frontier integration owner"],
  "coverage_tradeoff": "skips optional benchmark"
}
```

Never invent prices. Use null money/currency unless the caller supplies trustworthy pricing.

## Proportionality review

Before accepting the choice, compare goal stakes/ambiguity/change surface against selected verification depth, model mix, parallelism, and contingency. Recommend a cheaper or safer alternative when mismatched. Ask once only when the tradeoff is material; otherwise record `assessment: proportionate` and proceed.

Reforecast only after material scope, environment, or failure-class change. Track actual token/time/disk variance at completion; keep non-required opportunities in `optional_work` with separate costs and risks.
