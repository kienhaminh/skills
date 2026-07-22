# kienhaminh-skills

## 1.0.0

### Major Changes

- [`b8ec621`](https://github.com/kienhaminh/skills/commit/b8ec62179beb218fa67daf6b69f713552ba277c4) Thanks [@kienhaminh](https://github.com/kienhaminh)! - Make Graphflow provider-neutral with digest-locked coding-tool adapters and portable runtime defaults.

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

- [`36b13e5`](https://github.com/kienhaminh/skills/commit/36b13e593fecdf0b047a8d8d9a637e1cd20d2279) Thanks [@kienhaminh](https://github.com/kienhaminh)! - Replace workflow with graphflow, add ship, streamline skill routing, and prune superseded evaluation artifacts.

- [`2780df3`](https://github.com/kienhaminh/skills/commit/2780df3a6f00767b110b2305ba1440835b9ef003) Thanks [@kienhaminh](https://github.com/kienhaminh)! - Rename to-tdd to tdd and to-stories to stories, with updated display names.

### Minor Changes

- [`d720ea8`](https://github.com/kienhaminh/skills/commit/d720ea8dd5a7cee380029d7f2bd14545047c777a) Thanks [@kienhaminh](https://github.com/kienhaminh)! - Make every public skill portable across repositories with explicit invocation, completion, and validation contracts.
