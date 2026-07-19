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
