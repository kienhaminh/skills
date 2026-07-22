---
"kienhaminh-skills": major
---

Make Graphflow provider-neutral with digest-locked coding-tool adapters and portable runtime defaults.

This replaces the Codex-only execution path with `graphflow-agent-adapter-v1`, used by both ordinary
agent nodes and decomposition reviewers. Workflows now select abstract model classes and map them in
`runtime.json`; the bundled optional Codex CLI wrapper demonstrates compatibility while every other
tool supplies a wrapper that proves its own sandbox and structured-output controls. The runner now
regenerates, validates, and injects bounded shared-memory capsules immediately before agent dispatch.
Adapters declare network and credential needs, and executable validation rejects undeclared
capabilities before any node becomes active.

This is breaking because the default state/profile paths move from `.codex` to `.graphflow`, generated
branches use `graphflow/`, `model` becomes `model_class`, `goal_adapter` becomes `caller_adapter`, and
the `--codex-bin` runner options are removed. Existing workflows should remain at their current paths
until migrated, copy an adapter wrapper into `<workflow>/adapters/`, configure and digest-lock
`runtime.json.agent_adapter`, replace provider model IDs with `small`, `balanced`, or `frontier`, then
relock and revalidate the workflow before resuming.
