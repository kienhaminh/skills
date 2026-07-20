---
name: tdd
description: Turn one user story into an exhaustive test list and meaningful failing tests, without production implementation. Use for TDD, tests-first, test-case enumeration, or requests to convert a story into tests. Consume stories from $stories when available and hand red tests to $implement.
---

# User story to failing tests

Produce the red starting point: an agreed test list, runnable tests, and only the minimal stub needed
for meaningful failures. Stop before production implementation.

## Select one story

Use a pasted story or one story from `docs/plans/stories/<slug>.md`. Identify its actor, capability,
acceptance criteria, constraints, and open questions. If several stories are possible and the request
does not select one, ask which to use.

If acceptance criteria are absent, stop and invoke `$stories` when the user wants them derived.
Do not invent tests against an unagreed target.

## Enumerate before writing

Read [situation-catalogue.md](references/situation-catalogue.md) completely. Walk every applicable
row and give it one explicit disposition:

- **test** - write a test for the situation;
- **excluded** - use one allowed catalogue reason and name the owning layer or existing test.

Start from the acceptance criteria, then add applicable unhappy, boundary, authorization,
concurrency, persistence, queue, and cross-cutting cases from the catalogue. Present the list for the
user to veto before editing files.

Use this schema:

| # | Situation | Case type | Level | Source | Disposition |
| --- | --- | --- | --- | --- | --- |

Mark inferred cases separately from acceptance-criterion cases. A catalogue row left silent is a
coverage gap.

## Write meaningful red tests

Read `docs/TESTING.md` for file placement, naming, commands, infrastructure, and repository-specific
invariants. The repository guide wins on mechanics.

- Test observable behaviour, not private calls or implementation order.
- Give each test one behaviour claim and a descriptive name.
- Choose the lowest level that exercises the real subject. If the criterion concerns SQL, queue
  delivery, or another real dependency, do not fake that dependency away.
- For new code, add only the real signature and a `not implemented` stub so the suite compiles.
- For existing code, add no stub when the assertion can fail against current behaviour.
- Never write production logic or weaken an agreed criterion.

## Prove the red state

Run the exact focused command from `docs/TESTING.md` and inspect every failure. Accept only:

- an assertion mismatch caused by missing behaviour; or
- the deliberate `not implemented` failure from the minimal stub.

Fix broken imports, type errors, incorrect fakes, and unrelated failures before handoff. If required
infrastructure is unavailable, report the affected tests as written-but-unrun, never as proven red.

## Hand off

Return:

- test and stub paths plus the exact run command;
- the test-list dispositions, including explicit exclusions;
- key failure lines and why each red is meaningful;
- inferred unhappy paths, integration-level tests, ambiguity, and unavailable infrastructure;
- the contract `$implement` must satisfy without changing the tests.

Leave the story unchanged and the production behaviour unwritten.
