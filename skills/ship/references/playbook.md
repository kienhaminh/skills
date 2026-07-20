# Ship playbook

Use repository evidence to supply the literals for **Gate → Record → Commit → Publish**. This
reference defines discovery and safety mechanics; the repository owns commands, branch names, record
locations, and hosting conventions.

## Discover the contract

Read repository instructions and inspect:

```bash
git status --short --branch
git log --oneline -20
git remote -v
git remote show <remote>
```

Derive required local and CI gates, task-record locations, durable documentation owners, commit
convention, current head, push remote, remote default branch, and pull-request tooling. Record each
literal with its evidence. Memory and conventional names remain candidates until the checkout or
remote proves them.

## Gate

Build a matrix before mutation:

```text
gate | command or action | applicability | required | result | evidence
```

Include the repository-applicable build, static checks, lint or format checks, focused tests,
integration tests, changed-flow verification, and review. Inspect scripts before trusting their
names; a zero-work or wrong-package command is not evidence. Run gates against the exact intended
tree. Proceed when every required applicable gate is green and report unavailable optional checks as
limits.

## Record

When the repository has an active task record, follow its lifecycle. A common outcome shape is:

```markdown
## Outcome (YYYY-MM-DD)
<Implemented result and observable effect.>
<Deliberate cuts and remaining limits, when applicable.>
```

Move the record with a history-preserving Git operation when active and completed locations differ.
Update lessons and debt only when the work genuinely changes those records. Keep business/domain
documentation under its established sync process.

## Commit

Inspect intended paths, then stage them explicitly. Use `git add -A` only when the complete dirty tree
is proved to belong to this task. Recheck with:

```bash
git diff --cached --stat
git diff --cached
```

Derive message format from repository policy and recent history. If Conventional Commits are used,
prefer:

```text
type(scope): imperative subject

<why the change exists and the task or decision it satisfies>
```

After committing, prove the commit tree contains the gated files and unrelated working-tree changes
remain preserved.

## Publish

Resolve the remote default branch instead of assuming `main` or `master`:

```bash
git symbolic-ref --quiet --short refs/remotes/<remote>/HEAD
git ls-remote --symref <remote> HEAD
```

For a push, show the exact commit SHA, remote, head, and external effect. When a pull request is
requested, also confirm head and base differ and show the base plus proposed title/body. Obtain
approval before the first requested remote mutation.

Push without rewriting unrelated remote history unless force publication is independently
authorized:

```bash
git push -u <remote> <head-branch>
git ls-remote <remote> refs/heads/<head-branch>
```

When the user requested a pull request, use the repository's hosting tool to create or reuse the
matching pull request. A portable body is:

```markdown
## Goal
<observable outcome>

## What changed
- <material change>

## Verification
- `<command>` — <result>
```

Return the requested commit, pushed ref, or PR URL; proved SHA; gate evidence; record changes; and
remaining limits.
