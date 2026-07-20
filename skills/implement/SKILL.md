---
name: implement
description: Implement an agreed story, plan, or failing-test target in the Vietnam monorepo and prove the resulting behaviour. Use for requests to implement, write code, build a feature, or make red tests pass. Not for diagnosis-only work (use $debugging), tests-first design (use $to-tdd), or story slicing (use $to-stories).
---

# Implement

Make the agreed behaviour real with the smallest change that fits the current codebase. Prefer reuse
over new abstractions and evidence over claims.

## Pin the target

Read the red tests, selected story, or plan and state the behaviour it constrains. When no executable
target exists, write or borrow a focused check, or state explicit acceptance criteria before coding.
Do not implement against an unnamed target.

Read the nearest existing implementation, its tests, and owning configuration. Follow the repository
trust order in `docs/README.md`; current code and executable config outrank stale prose.

## Plan the smallest change

For a non-trivial edit, state:

- files and contracts to touch;
- callers and blast radius found by search;
- the smallest reuse or extension that satisfies the target;
- unresolved choices that would materially change the implementation.

Keep speculative features, generic wrappers, and unrelated cleanup out of scope.

## Follow repository rules

Read only the guides relevant to the change:

- `docs/CONVENTIONS.md` for placement, contracts, boundaries, and named exceptions;
- `docs/SECURITY.md` before changing auth, input, or secrets;
- `docs/OBSERVATION.md` before adding logs, health checks, or monitoring;
- `docs/TESTING.md` for real commands, test levels, and infrastructure;
- `docs/plans/tech-debt.md` for known failures that must not be mistaken for regressions.

Match surrounding naming, error shapes, comment density, UI patterns, and dependency direction. Reuse
the existing owner of a concept instead of creating a parallel one.

## Make the target green

Implement production behaviour; do not delete a case, loosen an assertion, or rewrite the target to
manufacture green. If an agreed test is wrong, stop and explain the conflict before changing it.

Run the narrowest affected checks first, then the supported broader gate. For previewable behaviour,
drive the changed flow end to end. Report infrastructure-dependent checks as unrun when their
dependencies are unavailable.

## Hand off

Report:

- changed files and the reason for each non-obvious choice;
- exact commands run and observed results;
- unrun checks, assumptions, and deliberate exclusions;
- any remaining debt or follow-up outside the target.

Invoke `$sync-docs` when durable business behaviour changed. Invoke `$ship` only when the user asks
to land the completed work.
