---
name: ship
description: Land finished work in a Git repository through Gate, Record, Commit, and Publish. Use when the user asks to close completed work, commit and push it, or open a pull request; use repository review workflows for reviewing an existing PR.
---

# Ship finished work

Apply **Gate → Record → Commit → Publish**. Read
[playbook.md](references/playbook.md) for repository discovery and command mechanics.

## Gate

Inspect repository instructions, branch or commit, upstream, dirty state, existing commits, and task
records. Discover the repository's actual build, static-check, test, changed-flow verification, and
review gates. Run every applicable required gate against the tree that will be shipped.

A red required gate keeps the work in progress. An unavailable required gate becomes a named blocker;
an unavailable optional surface becomes a reported limitation.

Complete Gate when each applicable check has a fresh result tied to the intended tree.

## Record

Follow the repository's task-record lifecycle. When an active plan or equivalent drove the work,
record a factual dated outcome, move it to the repository's completed state, remove only debt resolved
by this change, and add a lesson only when the task produced a reusable reasoning rule.

For work already recorded elsewhere, use the existing record and avoid creating empty ceremony.
Route durable business-document changes through the repository's documentation-sync process.

Complete Record when the final tree contains an accurate durable account of what landed and what was
cut.

## Commit

Stage only intended implementation and record files. Derive commit style from repository policy and
recent history. Recheck the staged diff, then create the minimum coherent commit set authorized by the
user.

Complete Commit when committed content equals the gated tree and unrelated working-tree changes
remain preserved.

## Publish

Use the discovery, confirmation, mutation, and idempotency mechanics in
[playbook.md](references/playbook.md). Execute only the requested publish actions; commit, push,
pull-request, merge, and deploy authority are independent.

Shipping is complete when the requested local commit, pushed branch, or pull request exists at its
proved SHA, all gate evidence and limitations are reported, and task records match that tree.
