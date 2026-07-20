---
name: tdd
description: Test-first an agreed behavior by enumerating its contract and producing meaningful failing tests; hand a proved red contract to $implement.
---

# Produce a meaningful red contract

Deliver an agreed test list, runnable tests, and only the minimal stub required for meaningful
failures. Production behavior remains for implementation.

## 1. Select one behavior

Use a pasted story or one selected from the repository's backlog. Identify actor, capability,
acceptance criteria, constraints, and open questions. Resolve story selection when several candidates
exist. Route missing acceptance criteria through `$stories` when the user wants them derived.

Complete selection when one agreed behavior and its observable boundaries are explicit.

## 2. Enumerate before editing

Read [situation-catalogue.md](references/situation-catalogue.md) completely. Walk every applicable row
and assign one disposition:

- **test** — the accepted contract defines the outcome; write a test;
- **excluded** — use an allowed catalogue reason and name the owning layer or existing test;
- **open** — the situation is applicable but expected behavior is not agreed; resolve it before
  writing that test.

Start with acceptance criteria, then add applicable unhappy, boundary, authorization, concurrency,
persistence, async, and cross-cutting cases. Mark inferred cases separately. Present the list for user
review before editing files when new inferred behavior materially expands the contract.

```text
# | Situation | Case type | Level | Source | Disposition
```

The catalogue supplies probes, not default product policy. Complete enumeration when every applicable
row has an explicit disposition and every material `open` row is resolved or returned as a contract
blocker.

## 3. Write meaningful failures

Read the repository's testing guide when present for placement, naming, commands, infrastructure, and
invariants.

- Test observable behavior with one claim per test.
- Choose the lowest level that exercises the real subject.
- Keep a real database, queue, filesystem, or network boundary when the criterion depends on it.
- For new code, add only the real signature and a `not implemented` stub needed to compile.
- For existing code, let assertions fail against current behavior when possible.

Complete writing when every `test` disposition maps to one runnable test and production logic remains
unchanged.

## 4. Prove red

Run the focused repository command and inspect every failure. Accept an assertion mismatch caused by
missing behavior or the deliberate minimal-stub failure. Repair imports, type errors, broken fixtures,
and unrelated failures before handoff. When required infrastructure is unavailable after exhausting
repository-supported setup, finish as `written-unverified`, name the blocker, and withhold a proved-red
handoff.

The proved-red branch is complete when each written test is meaningfully red for the intended missing
behavior. The limited branch is complete when every written test is mapped to its intended failure
but unavailable infrastructure is explicitly unverified. In both branches report paths, command,
dispositions, observed failures, inferred cases, unavailable checks, and whether `$implement` has a
proved contract or must wait.
