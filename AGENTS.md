# Repository rules

This repository is a skills.sh library. Each `skills/<skill-slug>/SKILL.md` is public, installable behaviour.

## Changeset policy

Create a Changeset in the same change whenever you add, remove, rename, or materially change a skill's instructions, trigger conditions, scripts, or public behaviour. Use:

```sh
npm run changeset
```

Select `kienhaminh-skills`, choose the release type, and write one concise user-facing summary. Do not manually edit the version in `package.json`; the release workflow does that.

- `patch`: corrections, clarifications, or backwards-compatible behaviour changes.
- `minor`: a new skill or substantial new capability.
- `major`: removed, renamed, or incompatible skill behaviour.

Do not create a Changeset for CI-only changes, local tooling, or a change that never reaches an installed skill. If a pull request changes `skills/**`, CI requires at least one new `.changeset/*.md` file.

## Release flow

1. A contributor or agent adds a Changeset with the change.
2. The pull request is reviewed and merged to `main`.
3. GitHub Actions creates or updates a `chore: version skills` pull request with the computed version and changelog.
4. Merging that release pull request creates the Git tag.

Never combine an ordinary feature change with generated version/changelog files unless you are intentionally merging the release pull request.

## Real-project validation

Develop and evaluate skills from this repository. Do not copy a draft skill into another repository. Link the source directory into the target project's local skill directory instead:

```sh
npm run link:project -- --project /absolute/path/to/project --agent codex --skill debugging
```

The linker refuses to replace a non-library skill. Use a fresh agent task after linking so the target harness discovers the current source. Follow [docs/REAL_PROJECT_EVALS.md](./docs/REAL_PROJECT_EVALS.md) for baseline-versus-skill evaluation and preserve only sanitized local artifacts.
