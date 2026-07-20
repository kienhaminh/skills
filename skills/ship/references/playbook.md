# Ship playbook

Exact commands and mechanics for the four steps. SKILL.md carries the reasoning; this carries the
literals that would clutter it. Verify commands against `docs/TESTING.md` if anything here looks stale
— the docs are the trust anchor, this file is a convenience copy.

## Gate — the checks, and the repo's traps

Run these before anything else. Any red one ends the run.

| Check | Command | Notes |
| --- | --- | --- |
| Type-check | `pnpm type-check` | Turbo-wide, meaningful. A type error here is yours — it must be green. |
| Unit tests | `pnpm --filter server test` | The real suite. **Not** root `pnpm test`. |
| Integration | `pnpm --filter server test:int` | Only if you touched/added `*.int-spec.ts` **and** the test DB is up (see `docs/TESTING.md`). Skip otherwise — don't fail the ship on a DB you didn't need. |
| Behaviour | `/verify` | Drive the actual flow the change affects end-to-end, not just tests. |
| Review | `/code-review` | Address real findings before landing. A confirmed finding is a red gate. |

**Traps (from `plans/tech-debt.md`), do not fall in:**
- `pnpm lint` currently does nothing — a green lint proves nothing; don't cite it as a gate.
- Root `pnpm test` also runs the dead v2 `backend` package and reports a **false green**. Always
  scope to `--filter server`.
- `pnpm dev` does not start the ingestion worker — if the change is worker-side, `/verify` must run
  the worker explicitly, not assume `pnpm dev` exercised it.

Only when every applicable row is green do you proceed to Record.

## Record — the literals

**Outcome section** (prepend to the plan before moving it):

```markdown
## Outcome (YYYY-MM-DD)
<What was done, in one or two sentences.> <What was cut and why, if anything.>
<Lesson worth adding to LESSONS.md, if any — and add it there too.>
```

Then move the file:
```bash
git mv docs/plans/active/<slug>.md docs/plans/completed/<slug>.md
```
(`git mv` keeps history; a plain move + re-add loses the rename.)

**LESSONS.md entry** (only if a reasoning-level lesson was paid for) — newest first, at the top of the
Rules section:

```markdown
## YYYY-MM-DD — <the rule, in a few words>
<One imperative line stating the rule.>
Why: <the incident that taught it, one line.>
```

Get today's date from the environment / `date +%F` — don't guess it.

## Commit

```bash
git add -A          # code + Outcome + LESSONS + tech-debt edit, staged together
git commit -m "type(scope): imperative subject" -m "<why + plan slug / AD-id it satisfies>"
```

- `type` ∈ `feat | fix | docs | chore | refactor | test | perf`. `scope` ∈ `server | web | db |
  contracts | tooling | …` — match what `git log --oneline -20` shows; don't invent a new scope
  vocabulary.
- Subject: imperative, lower-case, no trailing period, ~50 chars.
- The harness appends `Co-Authored-By` automatically — do not write it yourself.

## Publish

Branch check first — never PR from `master` into `master`:
```bash
git rev-parse --abbrev-ref HEAD    # must not be 'master'
```
If it is `master`, stop and ask the user which branch to land on.

Push and open the PR (base = `master`, the repo's main branch):
```bash
git push -u origin "$(git rev-parse --abbrev-ref HEAD)"
gh pr create --base master --title "type(scope): subject" --body "$(cat <<'EOF'
## Goal
<one line: what the user/system can now do that it couldn't before>

## What changed
<2–4 bullets, the substance, not a file list>

## Verification
<the gate evidence: which tests, what /verify showed>

Closes: docs/plans/completed/<slug>.md
EOF
)"
```

- PR title mirrors the commit subject.
- The harness appends the "Generated with Claude Code" line to the PR body — don't hand-write it.
- `gh` is authenticated (`gh auth status`) and the remote is `origin`. If `gh` errors on auth, report
  it and stop — don't fall back to a raw API call with a token.
- Report the PR URL back to the user as the final result.
