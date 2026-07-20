---
name: ship
description: Land finished work in the Vietnam monorepo through Gate, Record, Commit, and Publish. Use when the user asks to ship, close, commit and push, or open a PR for completed work. Not for implementation, diagnosis, standalone docs sync, or review of an existing PR.
---

# Ship

Close completed work in this order: **Gate -> Record -> Commit -> Publish**. Read
[playbook.md](references/playbook.md) for exact commands and repository-specific mechanics.

## Gate

Inspect branch, dirty state, existing commits, and any active plan. Run every applicable gate from the
playbook: type-check, focused tests, changed-flow verification, and code review.

Stop on a red or unavailable required gate. Report the blocker; do not record completion, commit, or
publish. For already-committed work with no fresh task diff, gate the merged branch state and explain
why diff-specific review or verification does not apply.

## Record

When this work used an active plan:

1. prepend a factual dated Outcome;
2. move the plan from `docs/plans/active/` to `docs/plans/completed/`;
3. remove resolved tech-debt entries;
4. add a lesson only when the task produced a reusable reasoning rule.

Do not create a plan, Outcome, lesson, or empty commit for work already recorded elsewhere. Do not
edit `docs/design/domain.md` directly; invoke `$sync-docs` for durable business changes.

## Commit

Stage only the intended code and record files. Follow the repository's recent Conventional Commit
style and cite the governing plan or decision when one exists. Recheck the staged diff before
committing.

## Publish

Never publish from `master` into `master`. Prepare the final commit subject and PR title/body, show
them to the user, and obtain one confirmation before push and PR creation. Then follow the playbook,
prove the remote ref, and return the PR URL.

Commit, push, and PR authority do not imply merge or deploy authority.

## Finish

Report the landed commit/PR, gate evidence, recorded plan or lesson changes, and any unrun check or
remaining risk. Keep the conversation in the user's language and repository artifacts in English.
