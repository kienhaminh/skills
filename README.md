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
| [bootstrap](./skills/bootstrap/SKILL.md) | Establishes a codebase's architecture, conventions, docs, reuse boundaries, quality gates, and navigation map. | General-purpose, but expects the target repository's stack and docs to be inspected. |
| [brainstorming](./skills/brainstorming/SKILL.md) | Decomposes an ambiguous, high-stakes decision into a labelled problem tree and synthesizes a recommendation. | General-purpose; not a bug diagnosis or feature-planning workflow. |
| [debugging](./skills/debugging/SKILL.md) | Produces concise, evidence-bounded root-cause analysis with facts, inferences, alternatives, and uncertainty separated. | Currently adapted to the Vietnam monorepo and its `docs/DEBUG.md`. |
| [grill-me](./skills/grill-me/SKILL.md) | Turns a vague feature request into grounded alternatives, risks, and an implementation write-up before code is changed. | Project-adapted; uses the target repository's planning and domain-doc conventions. |
| [implement](./skills/implement/SKILL.md) | Converts an agreed story, plan, or red test into the smallest proven production change. | Currently adapted to the Vietnam monorepo. |
| [sync-docs](./skills/sync-docs/SKILL.md) | Reconciles durable business documentation with implemented behaviour after a completed change. | Project-adapted; expects `docs/design/domain.md`. |
| [stories](./skills/stories/SKILL.md) | Slices a plan into an epic and behaviour-focused user stories with acceptance criteria. | Project-adapted; expects the `docs/plans/` and domain-doc layout. |
| [tdd](./skills/tdd/SKILL.md) | Converts a user story into meaningful failing tests and stops before production implementation. | Project-adapted; follows `stories`. |
| [workflow](./skills/workflow/SKILL.md) | Creates or runs a persistent, provider-neutral work graph with explicit authority, evidence, recovery, and integration. | General workflow infrastructure; needs an explicit `workflow_id`. |
| [worktree](./skills/worktree/SKILL.md) | Coordinates parallel Git worktrees while isolating ports, databases, containers, caches, logs, and ownership. | Broadly reusable; adapt the repository-specific doc references before use elsewhere. |

The scope column is intentional: a skill labelled **project-adapted** should be made generic or configured for another repository before treating it as portable. Do not silently apply Vietnam-specific paths or commands in a different project.

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
  agents/openai.yaml  # optional invocation metadata
  references/         # optional supporting material
  scripts/            # optional local helpers
  evals/              # optional reproducible, publishable benchmarks
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
