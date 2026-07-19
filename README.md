# Agent Skills

This repository is a Vercel [skills.sh](https://skills.sh) library for reusable agent skills. It intentionally starts with an empty `skills/` directory.

## Install this library

After this repository is pushed to GitHub, install its skills with:

```sh
npx skills@latest add kienhaminh/skills
```

To install one named skill only:

```sh
npx skills@latest add https://github.com/kienhaminh/skills --skill <skill-slug>
```

The installer lets the user select supported coding agents, including Codex. Set `DISABLE_TELEMETRY=1` before the command to opt out of skills.sh's anonymous install telemetry.

## Add a skill

Create a directory for each skill and place its instructions in `SKILL.md`:

```text
skills/
  <skill-slug>/
    SKILL.md
    scripts/          # optional helpers
    references/       # optional supporting material
```

Keep each skill self-contained and use a lowercase, hyphenated slug. No package publication or Vercel deployment is required: once the public GitHub repository contains a `SKILL.md`, it can be installed with the commands above and will be discovered by skills.sh after installs occur.

## Releases

Install dependencies once with `npm install`. Changes to an installable skill must include a Changeset; see [AGENTS.md](./AGENTS.md) for the release policy. On merge to `main`, GitHub Actions opens a version pull request. Merging that pull request updates the changelog and creates the release tag.

## Security

Review every third-party skill before installing it, and do not commit secrets to skill instructions or helper scripts.
