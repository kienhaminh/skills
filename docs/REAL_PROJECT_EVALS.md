# Real-project skill evaluation

Use the real project checkout as the task environment and this repository as the single skill source. Never copy a work-in-progress skill into the project.

## 1. Link the candidate skill

```sh
cd /Users/kien.ha/Code/skills
npm run link:project -- \
  --project /absolute/path/to/project \
  --agent codex \
  --skill debugging
```

The target receives a symlink at `.codex/skills/debugging`. Start a fresh Codex task after linking. Edits in this repository are immediately visible to that task.

Use `npm run doctor:project -- ...` to verify the link. The linker never overwrites or unlinks a skill it did not create.

## 2. Use a project-grounded evaluation card

Before running an agent, write a short local card under `.local-evals/` in this repository. Do not commit source code, secrets, customer data, or machine-specific paths.

```md
# <skill> — <sanitized scenario>

- Project revision: `<commit SHA>`
- Task: the exact user request, with sensitive details removed
- Constraints: read-only or allowed files; time limit; required test command
- Success checks: observable conditions that can be independently checked
- Rubric: correctness, safety, evidence, scope, and the task-specific outcome
```

Choose a task that already exists in the project: a real bug, a planned refactor, or an existing test failure. Pin the Git commit before each run.

## 3. Compare the same task fairly

For read-only tasks, run the exact same prompt twice in fresh agent tasks:

| Run | Setup | What to record |
| --- | --- | --- |
| Baseline | `npm run unlink:project -- ...` | response, commands, tests run, score |
| With skill | `npm run link:project -- ...` | same fields and score |

For mutating tasks, evaluate on two disposable branches or worktrees from the same pinned commit. This protects the working project; the skills remain live-linked and are never copied. Do not use one agent's prior response as context for the other run.

## 4. Grade what happened

Score only observable output:

- **Correctness:** required tests and acceptance checks pass.
- **Safety:** no disallowed file, service, data, or destructive command was touched.
- **Scope:** the diff is limited to the request.
- **Evidence:** claims cite inspected code, tests, logs, or documentation.
- **Skill-specific behaviour:** for example, debugging keeps diagnosis separate from a fix; worktree declares isolation; bootstrap preserves project conventions.

Keep the raw run and score locally in `.local-evals/`. Promote only a sanitized, reproducible fixture and rubric into `skills/<slug>/evals/` when it is safe to publish.

## 5. Finish cleanly

```sh
npm run unlink:project -- \
  --project /absolute/path/to/project \
  --agent codex \
  --skill debugging
```

The target project is left without copied skill files. Commit a Changeset only when the evaluated skill itself changes.
