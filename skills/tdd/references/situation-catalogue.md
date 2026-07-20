# Situation catalogue — walk every applicable row, dispose of each

The catalogue is a set of probes, not default product policy. Derive expected outcomes from accepted
criteria, repository rules, and existing contracts. When a probe is applicable but its expected
behavior is unspecified, mark it **open** and resolve the contract before writing that test.

Build the test list by **enumeration, not intuition**: walk the catalogue below, and for the behavior
under test, every row that could occur becomes a line with an explicit disposition —

- **→ test** — you will write a test for it, or
- **→ excluded** — with a reason from the allow-list at the bottom; or
- **→ open** — applicable, but the authoritative outcome is not yet agreed.

You do not write a test for every row — a pure function has no auth row — but you must *account for*
every applicable row. A row you neither test nor consciously exclude is a bug you shipped.

Start with the **Universal** section (applies to anything taking input), then add the sections that
match what the behavior is (a function, a query, an endpoint, a job). A story often spans several —
an endpoint that enqueues a job pulls in C and D and E.

---

## Universal — any behavior that takes input

| Dimension | Concrete situations to enumerate |
| --- | --- |
| Absence | `null`, `undefined`, missing field, empty string `""`, empty array/object |
| Empty vs blank | empty string vs whitespace-only (`"   "`, tab, newline) — often behave differently |
| Cardinality | zero items, exactly one, many; the ZOMBIES Z/O/M spine |
| Boundaries | min, max, max+1, off-by-one, the exact threshold on both sides |
| Duplicates | the same item twice in one input; case/whitespace variants that should collapse |
| Ordering | already-ordered, reverse-ordered, and whether output order is guaranteed (assert it) |
| Repetition | apply the operation twice; decide whether idempotency, duplication, or rejection is required |
| Determinism | repeat the same input; decide whether output ordering/content must be stable |

## Text and string input

| Dimension | Concrete situations |
| --- | --- |
| Casing | upper/lower/mixed collapse to one key where dedupe is the point |
| Whitespace | leading, trailing, **inner** (collapsed or preserved? — decide and pin), tabs, newlines |
| Diacritics | Accents and language-specific letters remain distinct unless the agreed contract normalizes them |
| **Unicode form** | The same visible text in **NFC vs NFD**; filesystems and input methods may emit either, so decide and pin normalization behavior |
| Injection-ish chars | quotes, `%`, `_` (SQL LIKE wildcards), backslash, angle brackets — for anything reaching SQL/HTML |
| Size | empty, one char, and very long (past a column limit if one exists) |

## Persistence / query behavior (→ the level where the database is real)

A faked query builder cannot exercise any of these — if the criterion is about *what the SQL does*, it
belongs at the level where the database is real, not a unit test that would "pass" against SQL that
throws. (Where that level lives and how to run it is in the repo's testing guide.)

| Dimension | Concrete situations |
| --- | --- |
| Not found | zero rows for the key; distinguish "no match" from "error" |
| Cardinality | exactly one row vs many; the many case with a `LIMIT` |
| Conflict | `ON CONFLICT` / unique-violation path; upsert updates vs inserts |
| Concurrency | two writers racing; lost update; exactly-once; needs an atomic conditional `UPDATE` or a dedupe key, not a check-then-write |
| Result ordering | order-by correctness **and** tie-breaking when scores are equal |
| Matching edges | case-fold, fuzzy/similarity threshold (a hit just above it, a miss just below), partial match |
| Pagination | first page, last page, past-the-end (empty), `limit 0`, offset beyond count |
| Null semantics | a nullable column read as a flag — null vs set (e.g. an "is it live yet" check keyed off whether a snapshot column is populated) |
| Rollback | a transaction that fails mid-way leaves no partial write |

## HTTP endpoint / controller

| Dimension | Concrete situations |
| --- | --- |
| Happy | correct status code **and** response body shape |
| Auth ladder | unauthenticated, authenticated-but-not-authorized, and authorized; assert the repository-defined outcome for each |
| Guard wiring | the right guards are present **and in the right order** (an authz guard needs the authn guard's `req.user` first) |
| Path/param validation | missing param, malformed id, wrong type |
| Body validation | missing required field, wrong type, extra fields, wrong content-type |
| Not found | the referenced resource does not exist; assert the contract-defined response |
| Conflict / duplicate | submit the same action twice; decide whether conflict, idempotent success, or duplication is required |
| Side-effect timing | an async constraint ("must not block") → assert the slow work is **not** done in-request |

## Queue / async / job

| Dimension | Concrete situations |
| --- | --- |
| Enqueue cardinality | assert the contract-defined number of jobs for the success path |
| Rejected path | assert the contract-defined queue side effect for validation, authorization, conflict, and missing-resource outcomes |
| Payload | the job carries the right payload shape |
| Dedupe | a duplicate trigger; test dedupe, duplication, or rejection only when the contract chooses one, otherwise mark it open |
| Enqueue failure | the queue rejects; test surfacing, retry, compensation, or tolerance only when the contract defines it, otherwise mark it open |
| Job runs | the handler actually runs and produces the observable effect → **integration**, separate from "was enqueued" |

## Cross-cutting — always ask these of every story

- **The unhappy path the story omitted.** Probe what happens when the success path cannot complete.
  Derive an outcome from an authoritative contract or keep the situation open for a product decision.
- **The authorization angle.** Who must *not* be able to do this, and what do they get?
- **The concurrency angle.** What if this runs twice at once? Even if you leave it to integration, name
  it — a silently-absent concurrency test reads as "covered".
- **The empty-input angle.** Decide whether empty input is rejected, accepted as a no-op, or produces
  an empty result; keep unspecified semantics `open`.
- **The codebase's own invariants.** Reuse the rules existing tests already lock — a canonical form for
  a key, a dedupe key matched by plain equality, an is-live flag keyed off a nullable column. A story
  that would break one of these needs a test that pins the invariant. (The concrete ones for this repo
  are listed in the repo's testing guide / domain doc — read them there rather than guessing.)

---

## Valid reasons to exclude a row (anything else means: write the test)

1. **Statically impossible** — the type system already forbids it (e.g. no `null` test for a
   non-nullable `string` param, absent an `as any` that would test TypeScript, not the story). Say so.
2. **Not this unit's responsibility** — the situation is real but handled by a different layer; name
   that layer (e.g. "an empty query is rejected by the request-validation layer, not here"). This is
   itself a finding worth surfacing in the handoff.
3. **Already locked by an existing test** — cite that test file.
4. **Genuinely out of the story's scope** — beyond the acceptance criteria *and* not a latent bug the
   behavior would hit. If it *is* a plausible latent bug (like NFC/NFD for a dedupe key), keep it
   open for the user to rule on rather than dropping it or encoding an outcome.

An exclusion is a sentence in the test plan, not a silence. If no exclusion applies and the expected
outcome is agreed, the row is a test you owe. If the outcome is not agreed, keep it `open`; a red test
cannot decide product policy.
