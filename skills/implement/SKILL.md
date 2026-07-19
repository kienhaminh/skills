---
name: implement
description: Write the production code for a story, plan, or red tests in the Vietnam monorepo — making failing tests green (or a stated target real) by following the repo's conventions and disciplined engineering, then proving it works. Use when the user says "implement this", "viết code cho…", "làm tính năng X", "code this story", "make these tests pass", "triển khai", or hands over a plan/story/failing suite to build. Follows to-tdd. NOT for diagnosing a bug (→ debugging), writing tests first (→ to-tdd), or slicing a plan into stories (→ to-stories).
---

# Implement

Turn an agreed target — red tests, a story, or a plan — into working production code. The discipline
is not "produce code that looks right"; it is **make the observable behaviour real, prove it, and
leave the codebase looking like the code already there wrote it.** Code that passes because you
weakened its test, or that works but ignores the repo's grain, is a defect that hasn't surfaced yet.

**Simplest = least new code, leaning on what the codebase already provides.** This is not "write it
raw" — it's the opposite. The safe change *reuses* the repo's existing config, framework setup,
utilities, and conventions so you add as little of your own as possible, customise as little as
possible, and touch as few places as possible. Least new code, fewest custom knobs, smallest blast
radius: that is what stays easy to maintain, easy to change, and cheap to fix when something breaks.
Reinventing what a config or an existing helper already does — a bespoke variant beside a shared
one — is the *complex* choice, even when it feels more direct. When two solutions both pass, the one
that adds less and reuses more wins.

Input is usually the red tests from `to-tdd`. Degrade gracefully: no tests → first **pin the target**
(borrow/write a check, or at minimum state the acceptance criteria you're coding against) before
writing a line. Never code blind against a target no one named.

## The loop

1. **Read the target and the neighbours** — the tests/story, then the code that already does the
   nearest thing.
2. **State the plan** — smallest correct change, blast radius, open questions. Get a nod before a
   nontrivial edit.
3. **Write the code** — bound by the repo's rules; match the surrounding grain.
4. **Make it green by building, never by bending the test.**
5. **Prove it** — run, don't assert. Green output + evidence.
6. **Hand off** — what changed, what's proven, what's left.

## 1. Read the target and the neighbours

Read the tests (or story/plan) for the *behaviour* they constrain. Then read the code that already
solves the closest problem — the sibling service, the neighbouring tool, the existing controller.
**Trust order (`docs/README.md`): the code wins over any doc.** You are matching what is actually
there, not what a doc claims. This is the "scientific" core — evidence over spec, the existing code
as ground truth.

## 2. State the plan before a nontrivial edit

Smallest change that makes the target real — no speculative abstraction, no scope the target didn't
ask for (MVP cap; the repo defers what isn't needed yet). For anything beyond a one-liner, say up
front: **what you'll touch** (`file:line`), **blast radius** (who else calls this — search, don't
guess), and **anything uncertain** with 2–4 options, not a silent assumption. A hidden assumption is
a bug you chose not to mention.

## 3. Write the code — bound by the repo's rules

These are properties of *this* codebase; read them, don't re-derive them:

- **`docs/CONVENTIONS.md`** — contracts once in zod, parse-at-the-edge, service-not-controller,
  interface+Symbol for anything swappable, boundary-shaped auth, frontend route-handler boundary.
  Binds every edit.
- **`docs/SECURITY.md`** — before touching auth, input, secrets, or the 4 open gaps it lists.
- **`docs/OBSERVATION.md`** — before adding a log, health check, or monitoring dep (mostly: don't).
- **Frontend theme / design** — match what `apps/web` *actually* does: plain Tailwind, no custom
  tokens or CSS variables, no custom fonts (`app/globals.css` is bare). The `docs/design/` files
  are **not authoritative yet** (nothing there is implemented and the two disagree on the palette —
  see its README) — don't cite them as binding. Reuse the existing component and class patterns; if
  a new UI genuinely needs a colour/token the app hasn't set, surface the choice, don't invent one.

Match the grain: naming, comment density, error shape, file placement of the code beside yours. A
non-obvious line carries its *why* with a citation (`AD-8`, `spec §9`), never a restatement of what
it does. Two deliberate exceptions live in `CONVENTIONS.md` (the 5× `parseOrThrow`, the interim
`KnowledgeController` scope) — read them so you neither "fix" nor copy them.

## 4. Make it green by building, never by bending the test

The test is the specification `to-tdd` committed to. You satisfy it by writing the behaviour it
demands. Editing the assertion, loosening a matcher, or deleting a case to reach green **inverts the
whole point** — it proves only that you can make two things agree. If a test looks genuinely wrong,
stop and say so; don't quietly rewrite it. Fill the stub's real logic; keep methods doing one thing.

## 5. Prove it — run, don't assert

Green is a fact you observe, not a claim you make.

- Run the affected suite and read the output — `docs/TESTING.md` has the real commands and the split
  (unit `pnpm --filter server test`; int-specs need the test DB and don't ride `pnpm test`).
- **Known traps (`docs/plans/tech-debt.md`), or you'll report a false green:** root `pnpm test` also
  runs the dead v2 package — only the `server` numbers count. `pnpm lint` is a silent no-op — it
  proves nothing. `pnpm type-check` *is* real — a type error there is yours.
- Previewable frontend/server change → drive it end-to-end (the `verify` skill / the preview flow in
  `CLAUDE.md`), not just a passing test.
- Int-spec written but the test DB is down → report it written-but-unrun, never as green.

## 6. Hand off

- **What changed** — the files, and the one-line why for each non-obvious choice.
- **What's proven** — the command you ran and its result (paste the key lines), not "tests pass".
- **What's left** — anything unproven (int-specs unrun, a preview not driven), assumptions you made,
  and follow-ups you deliberately left out of scope.
- **Durable behaviour change?** Offer `sync-docs` to fold it back into `docs/design/domain.md`.

## Anti-patterns

- **Bending the test to green** — the cardinal sin; see step 4.
- **Reporting a false green** — trusting root `pnpm test`, `pnpm lint`, or an unrun int-spec as proof.
- **Ignoring the grain** — a new pattern where a sibling already set one; logic in a controller or a
  tool instead of the shared service; a hand-typed shape contracts already owns.
- **Over-building** — an interface, a config knob, a layer, or a bespoke helper beside an existing
  one, that the target never asked for. Least new code leaning on the repo's setup wins.
- **Silent assumptions** — coding past an ambiguity instead of surfacing it with options.
- **Asserting instead of running** — "this should work" with no output to back it.
