---
name: to-tdd
description: Turn a user story into failing tests first (TDD) — an exhaustively enumerated test list, then real red tests left for the implementer, no production code. Triggers: "do TDD", "write tests first", "test-driven", "turn this story into tests", "sinh test từ user story", "liệt kê test case", or a story handed over with "what tests does this need?". Follows to-stories.
---

# User story → failing tests (TDD)

A user story says *what someone can do and how we'll know it works*. TDD turns that "how we'll
know" into executable tests **written before the code exists**, so the tests are a specification
the implementer works against, not a report card graded afterwards. This skill takes one story and
produces the red starting point: a test list, real runnable tests in this repo's style, and a stub thin
enough that the tests fail on the *behaviour that's missing* rather than on a typo. Then it stops —
the implementer (a person or another agent) makes them green. Writing the implementation here would
defeat the point: a test you wrote to pass code you already wrote proves nothing.

The value is in the translation, and it is easy to fake. Restating "acceptance criterion 1" as
`it("meets acceptance criterion 1")` produces nothing — no one can tell from the name what broke, and
the criterion's edges went untested. Read the criterion for the **behaviour it constrains**, then
write tests a reader could learn the behaviour from.

## The loop

1. **Locate the story** and read its acceptance criteria — those are your seed test list.
2. **Build the test list** — expand each criterion into concrete cases (happy, unhappy, boundary), and
   decide the test level for each (unit vs integration). Show it to the user before writing tests.
3. **Write the tests** in the repo's style, and a minimal stub so red is *meaningful*.
4. **Run them and prove red** — confirm each fails for the absence of behaviour, not a broken import.
5. **Hand off** — tell the user what's red, why, and what the implementer must do to turn it green.

## 1. Locate the story

Input is usually one story (S1, S2, …) inside `docs/plans/stories/<slug>.md`, the output of the
`to-stories` skill. A story there looks like:

```
### S3 — Admin can publish one draft end-to-end
**As an** admin, **I want** to publish a reviewed draft, **so that** it appears on the public wiki.
Acceptance criteria:
- [ ] POST /admin/publish/:draftId returns 202 and enqueues a publish job.
- [ ] Publishing a draft that's already live returns 409, no second job.
- [ ] A non-admin token gets 403.
Constraints: publish is async via pg-boss; the endpoint never blocks on the snapshot build.
```

If the file has several stories, ask which one — do one story per invocation; a story is the unit of
behaviour that maps cleanly to a focused test suite. A story pasted straight into chat works too; map
whatever's there onto *actor / capability / criteria / constraints*. If there are no acceptance
criteria at all, say so and offer to derive them first (that's a `to-stories` job) rather than
inventing tests against a target no one agreed to.

Read `Constraints` carefully — they usually dictate the **test level**. An "async via a queue"
constraint means the happy path is really about a *job being enqueued*, which a faked-queue test can
assert; the job actually *running* is a real-infra concern one level up. A "matched by plain equality"
constraint means casing/whitespace is load-bearing and deserves its own case.

## 2. Build the test list first — by enumeration, not intuition

Kent Beck's discipline: before writing any test, write the *list* of tests you intend to write. It's
cheap to reorder and argue with a list, expensive to reorder written tests. But the list must be
**exhaustive, not a sampler** — the tests are the whole specification, so a situation you don't list is
a situation no one will ever test. The failures this skill exists to catch (the NFC/NFD dedupe fork,
the 409 path that still enqueues a job, the concurrent double-publish, the missing-token 401 collapsed
into 403) are precisely the ones an author "picking the interesting cases" skips. So don't pick — walk
a catalogue and account for everything.

**The procedure:** open **`references/situation-catalogue.md`** and walk every section that matches
what this behaviour is (a pure function → Universal + Text; a query → add Persistence; an endpoint →
add HTTP; a job → add Queue; plus Cross-cutting for all). For **each applicable row**, add a line to
the test list with a disposition — either **→ test** (you'll write one) or **→ excluded** with one of
the four allowed reasons in the catalogue. The rule that makes this real: *a row you neither test nor
consciously exclude with a reason is a gap you shipped.* "Unlikely" and "edge case" are not reasons —
they're the silence the catalogue exists to break.

You will not write a test for every row — a pure normalizer has no auth row, a total function over
`string` has a thin Exceptions column — but you must *dispose of* every applicable row on the page, so
the exclusions are as visible as the tests. That visibility is the deliverable: the reader sees not
just what you tested but what you decided not to, and why.

Present the list as a table the user can veto — every applicable situation as its own row, level and
disposition explicit:

| # | Situation | Case type | Level | From | Disposition |
| --- | --- | --- | --- | --- | --- |
| 1 | publish a not-live draft returns 202 and enqueues exactly one job | happy | unit (fake queue) | AC1 | → test |
| 2 | already-live draft returns 409 **and enqueues zero jobs** | unhappy | unit | AC2 | → test |
| 3 | unknown draftId returns 404, enqueues nothing | unhappy (inferred) | unit | catalogue: HTTP not-found | → test |
| 4 | no token → 401 (distinct from 403) | auth | unit (guard) | catalogue: auth ladder | → test |
| 5 | valid non-admin token → 403 | auth | unit (guard) | AC3 | → test |
| 6 | the enqueued job actually runs and writes a snapshot | scenario | integration (real queue) | AC1 + Constraint | → test |
| 7 | two concurrent publishes still enqueue once | concurrency | integration | catalogue: queue dedupe | → test (flag: needs singleton key) |
| 8 | malformed/oversized body | validation | — | catalogue: body validation | → excluded: DTO layer (`z` schema), not this handler |

Rows 3, 4, 7 came from the catalogue, not the story — that is the enumeration working. Row 8 is
excluded, but *visibly*, with the layer that owns it named. Getting this agreed *before* writing tests
is the highest-leverage checkpoint: a missing row here is a missing test forever, and every line after
compounds the omission.

## 3. Write the tests

The *mechanics* — where a test file goes, how to name and run it, the config traps, and the fake
patterns to copy — are properties of this codebase, not of TDD, so they live in the repo's own testing
guide: read **`docs/TESTING.md`** before writing the first test, and follow whatever it says (if it and
this skill ever disagree on a mechanic, the repo doc wins — it's read from the actual config). This
skill deliberately holds no file paths, suffixes, or commands; it teaches the thinking, the repo teaches
the wiring. The principles below are what make the tests *good* rather than merely present:

**Test the behaviour, not the implementation.** Assert on what the caller observes — return value,
status code, thrown error, the row that ends up in the DB — never on which private method got called
or in what order. A test coupled to internals goes red on a refactor that changed nothing observable,
which trains everyone to ignore red. The story is about behaviour; keep the test there too.

**One behaviour per test, named as a claim about that behaviour.** `it("upper-cases so an agent's
casing can't fork a type")` tells the next reader what breaks and why it matters; `it("test 1")` and
`it("works")` tell them to go read the body. Arrange-Act-Assert, with the three phases visible. If a
test needs three unrelated assertions, it's usually three tests.

**Make the red meaningful — this is the crux.** A test that fails with `Cannot find module` or a
TypeScript compile error is *not* a real red: it's failing because the code doesn't *parse*, not
because the behaviour is *absent*, and it hides whether your assertion is even right. So:

- **New code that doesn't exist yet:** write the minimal *stub* — the real signature/class, every
  method throwing `new Error("not implemented")` (or returning a deliberately wrong value). This is
  design, not implementation: you're committing to the contract the implementer must satisfy, and it
  makes the suite compile so red comes from your `expect`, not from `tsc`. Keep it to signatures; put
  no logic in it.
- **Behaviour added to existing code:** no stub needed — the assertion fails on its own against the
  current code. Verify the failure is your assertion, not an unrelated break.

**Pick the test level honestly — this is a judgement, not a lookup.** Test a behaviour at the altitude
where it actually lives. When a criterion is really a claim about *what a real dependency does* — what
the SQL computes, whether the queue delivers, what the network returns — a test that fakes that
dependency proves nothing: the fake happily returns whatever you set up, "passing" against real code
that would throw. Those belong at the level where the dependency is real. A criterion about a pure
transform, a guard, or a parser has no such dependency and belongs at the fast, faked level. The litmus
question: *would this test still catch the bug if I faked the very thing the criterion is about?* If no,
raise the level. (How this repo names and locates the two levels is in `docs/TESTING.md`.)

## 4. Run them and prove red

Run the suite and read the output — don't assume (the commands are in `docs/TESTING.md`). If a level
needs infra that isn't up, say those tests are written-but-unrun rather than reporting a false green.

For each test, confirm the failure reason is the *missing behaviour*: an assertion mismatch, or your
stub's `not implemented` throw. If instead you see `Cannot find module`, a `TS` error, or a fake that
didn't match the call chain, the red is fake — fix the stub or the fake and rerun. A TDD handoff whose
tests are red for the wrong reason is worse than none: the implementer makes the import resolve, sees
green, and ships untested code.

Capture the actual failure lines to show the user — proof the tests run and fail as intended.

## 5. Hand off

Leave the production code unwritten. Tell the user, concisely:

- **Where the tests are** and how to run them (the exact command).
- **What's red and why** — paste the key failure lines; name which are assertion-red vs stub-throw-red.
- **What the implementer does next** — the stub file(s) to fill, the contract the tests pin down, and
  the order to make them green (usually the happy case first, then exceptions, then boundaries).
- **Judgement calls worth their attention** — the situations you enumerated but *excluded* (with the
  layer that owns each), the unhappy paths you inferred beyond the story, any criterion too vague to
  test as-is, and any test placed at integration level (so they know it won't run without the test DB).
  The exclusions matter as much as the tests: they're where you decided coverage stops, and the reader
  should get to overrule you. The rest is mechanical.

## Anti-patterns — the whole point is to avoid these

- **Tests that only pass** — asserting the stub's `not implemented` throw and calling it a test. That
  pins nothing; the real assertion must describe the *wanted* behaviour and therefore be red now.
- **Writing the implementation too** — if the code is already green, you skipped TDD; the test proves
  only that you can write two things that agree.
- **One test per criterion, no more** — the criterion is the headline; the untested edges are where
  the bug ships. Walk the catalogue and enumerate them.
- **A sampled test list** — "I covered the interesting cases" is how the NFC/NFD fork and the
  enqueue-on-409 bug ship. Enumerate every applicable catalogue row; make the exclusions visible.
- **Restating the criterion as the test name** — `it("meets AC2")`. Name the behaviour.
- **Faking away the thing under test** — a unit test with a fake DB "covering" a SQL criterion. Raise
  it to integration.
- **Rewriting the story** — this skill reads the story and writes tests; it never edits the story file.
