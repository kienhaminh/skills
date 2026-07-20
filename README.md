# kienhaminh/skills

A practical library of reusable agent skills for structured thinking and software engineering. Skills are small instruction bundles that give an AI coding agent a repeatable method for a specific kind of task: framing an uncertain idea, diagnosing a failure, turning a plan into testable work, coordinating worktrees, or keeping durable documentation truthful.

This repository is the source of truth. It is distributed through [Vercel skills.sh](https://skills.sh) and can also be live-linked into a local project while you develop or evaluate a skill.

## Install

Install the library into an Agent Skills-compatible coding harness:

```sh
npx skills@latest add kienhaminh/skills
```

Install one named skill only:

```sh
npx skills@latest add https://github.com/kienhaminh/skills --skill <skill-slug>
```

The installer lets you select supported agents, including Codex. Set `DISABLE_TELEMETRY=1` before the command to opt out of skills.sh anonymous install telemetry.

## Skills

| Skill | What it provides | Scope |
| --- | --- | --- |
| [bootstrap](./skills/bootstrap/SKILL.md) | Maps and rehabilitates a repository from live evidence. | Discovers stack, documentation, commands, and agent conventions from the target repository. |
| [brainstorming](./skills/brainstorming/SKILL.md) | Decomposes an ambiguous decision into a labelled problem tree and one synthesis. | General reasoning; routes feature briefs and concrete failures to their dedicated skills. |
| [debugging](./skills/debugging/SKILL.md) | Produces evidence-bounded root-cause analysis without silently implementing a fix. | Uses the target repository's own debugging and verification contract. |
| [graphflow](./skills/graphflow/SKILL.md) | Creates and runs persistent verified work graphs. | User-invoked Codex orchestration with repository-proved execution and delivery policy. |
| [grill-me](./skills/grill-me/SKILL.md) | Turns a vague feature request into grounded alternatives, risks, and an implementation brief. | Discovers planning, provenance, and product constraints from the target source. |
| [implement](./skills/implement/SKILL.md) | Converts an agreed story, plan, or red test into the smallest proven production change. | Discovers owners, commands, and gates from the target repository. |
| [ship](./skills/ship/SKILL.md) | Gates, records, commits, and publishes finished work. | Discovers task lifecycle, Git policy, remote, base branch, and hosting mechanism. |
| [stories](./skills/stories/SKILL.md) | Slices an agreed plan into behavior-focused stories and acceptance contracts. | Uses the repository's existing planning owner and terminology. |
| [sync-docs](./skills/sync-docs/SKILL.md) | Audits or updates durable documentation against implemented behavior. | Discovers durable owners and keeps audit-only invocations read-only. |
| [tdd](./skills/tdd/SKILL.md) | Turns one accepted behavior contract into meaningful failing tests. | Uses repository-owned test layers and leaves missing product semantics open. |
| [worktree](./skills/worktree/SKILL.md) | Coordinates parallel Git worktrees with explicit resource isolation and ownership. | Discovers branch, path, dependency, environment, and cleanup policy. |
| [writing-great-skills](./skills/writing-great-skills/SKILL.md) | Audits skills for predictable invocation and execution. | User-invoked authoring and evaluation rubric. |

Public skills discover repository-owned paths, commands, and policy from the target checkout. A
runtime-specific surface is named explicitly in its skill contract, such as Graphflow's Codex storage
and executor adapter. Project-specific behavior belongs in that repository's instructions or
evaluation fixture, not in the reusable skill contract.

## Develop and evaluate on a real project

Do not copy a draft skill into a target project. Create a safe local symlink from the project's agent-skill directory back to this repository:

```sh
# Link one skill into a Codex project.
npm install
npm run link:project -- \
  --project /absolute/path/to/project \
  --agent codex \
  --skill debugging

# Verify or remove only the link created by this library.
npm run doctor:project -- \
  --project /absolute/path/to/project \
  --agent codex \
  --skill debugging
npm run unlink:project -- \
  --project /absolute/path/to/project \
  --agent codex \
  --skill debugging
```

The linker supports `codex` (`.codex/skills`), `claude` (`.claude/skills`), and `agents` (`.agents/skills`). It refuses to overwrite an existing skill and removes only symlinks it owns. Start a fresh agent task after linking so the harness discovers the current source.

For a fair real-project evaluation, pin a project commit and compare the same sanitized task in fresh baseline and with-skill runs. Read [the evaluation protocol](./docs/REAL_PROJECT_EVALS.md) for handling read-only versus mutating tasks, scoring observable outcomes, and retaining only non-sensitive evidence.

## Repository layout

```text
skills/<skill-slug>/
  SKILL.md            # instructions and trigger boundary
  agents/openai.yaml  # invocation metadata
  references/         # optional supporting material
  scripts/            # optional local helpers
  evals/              # reproducible forward tests and publishable evidence
```

Skills should use lowercase, hyphenated slugs and remain self-contained. Do not put secrets, customer data, or machine-specific paths in instructions, references, or published evaluation artifacts.

## Contributing and releases

Install dependencies with `npm install`. When an installable skill changes, create a Changeset:

```sh
npm run changeset
```

Choose `patch` for compatible corrections, `minor` for a new skill or substantial capability, and `major` for removal, rename, or incompatible behaviour. Do not edit the package version manually.

Pull requests that change `skills/**` require a new Changeset. After merge to `main`, GitHub Actions creates or updates a version pull request; merging it updates the changelog and creates the release tag. See [AGENTS.md](./AGENTS.md) for the repository rules.

## Security

Review third-party skills before installation. Treat skill instructions and helper scripts as executable guidance: inspect their files, avoid secrets, and run only commands that are appropriate for the target project.
