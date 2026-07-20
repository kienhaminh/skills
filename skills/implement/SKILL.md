---
name: implement
description: Implement an agreed story, plan, or failing-test target and prove the resulting behavior. Use when an accepted contract authorizes production changes; route diagnosis-only work to $debugging and test design to $tdd.
---

# Implement an agreed target

Make the accepted behavior real with the smallest coherent change that fits the current repository.

## 1. Pin the target

Read the selected story, plan, failing tests, or explicit acceptance criteria. Read repository
instructions, the nearest implementation and tests, and the owning configuration. When no executable
target exists, establish one focused check or explicit acceptance contract before editing.

Complete this phase when expected behavior, failure behavior, exclusions, and proof command are
named.

## 2. Find the smallest owner

For a non-trivial edit, identify:

- contracts and files that own the behavior;
- callers and blast radius found by search;
- the smallest reuse or extension that satisfies the target;
- choices that materially change implementation or authority.

Follow repository guides relevant to the change—conventions, security, observability, testing, known
debt, and release policy—when present. Match existing naming, error shapes, UI patterns, dependency
direction, and comment density.

Complete this phase when each planned edit has one owner and unrelated cleanup or speculative
features are outside the change set.

## 3. Make the target green

Implement production behavior while preserving the agreed test contract. If a target is incorrect,
surface the exact conflict and obtain a contract decision before changing it.

Run the narrowest affected checks first, then every supported broader gate applicable to the change.
For previewable behavior, exercise the changed flow end to end. Mark infrastructure-dependent checks
as unrun when their dependencies are unavailable.

Complete implementation when the target passes for the intended reason, affected existing behavior
still passes, and the final diff contains only accepted scope.

## 4. Hand off

Report changed files, material design choices, exact commands and observed results, unrun checks,
assumptions, deliberate exclusions, and remaining debt. Route durable behavior changes through the
installed documentation-sync skill when one exists. Invoke `$ship` only when the user asks to land
the work.

Complete handoff when every changed path, verification result, unrun surface, and remaining limit is
accounted for and no claim exceeds its evidence.
