# Read-only diagnosis: concurrent counter undercount

## Facts established from the fixture

- The incident is limited to concurrent requests: two successful increments can leave the counter one higher rather than two; both audit events are present, no repository error is logged, and a later read observes the lower value (`incident.md:3`).
- `CounterService.increment` performs a repository read, awaits audit observation, derives `current.value + 1`, and then writes that absolute value (`src/counter.service.ts:13-18`).
- The repository contract exposes only independent `read` and `write` operations. The visible contract does not state that either operation, or the full read/write sequence, is transactional, conditional, or serialized (`src/counter.service.ts:1-4`).
- The project documentation says current code is the highest-trust source and requires read-only analysis because the production-level concurrency condition is slow to reproduce locally (`docs/README.md:3-6`). The absence of recorded counter-consistency debt is not evidence that the current sequence is safe (`docs/plans/tech-debt.md:3`).

## Causal mechanism

The strongest explanation is a lost update. Two calls can both complete `repo.read(id)` before either call reaches `repo.write(id, next)`. Each call then holds the same `current.value`, emits its audit event, calculates the same `next`, and successfully writes that same value. The second write overwrites an equal value rather than failing, so both requests can return success while the stored counter advances once.

The awaited audit call widens the interval between read and write, making this interleaving more likely, but it is not required for the anomaly. The defect is the read-modify-write operation being expressed as separate operations without a visible atomicity or conflict-detection guarantee.

## Alternatives considered

- A repository implementation might independently provide per-key serialization, an implicit transaction, or conditional write semantics. That would prevent this specific lost-update schedule; the interface and fixture do not establish such a guarantee.
- An audit sink could be duplicated or decoupled from the request outcome. This could explain two audit events, but it does not by itself explain the final value being exactly one increment low when both requests succeed.
- A stale/cached later read could report a lower value despite two durable writes. This remains possible without repository/read-path details, but it would not explain why the symptom occurs only under concurrency as directly as the visible read-modify-write race.
- A later writer outside `CounterService` could overwrite the counter. No evidence in the provided project establishes such a writer.

## Confidence

High confidence that the visible service has a lost-update vulnerability under concurrent invocations. Moderate confidence that it is the incident's actual production cause: the observed symptoms align exactly, but the repository implementation and deployment behavior are outside the fixture.

## Evidence still needed

- The concrete `CounterRepository` implementation, including the SQL/query shape and transaction isolation/locking behavior for `read` and `write`.
- Request traces for two affected request IDs, with read values, write values, timestamps, and counter ID, to show both reads saw the same prior value and both writes used the same next value.
- Database/audit correlation to confirm the two audit events correspond to the two successful calls and not retries or asynchronous duplication.
- The topology and storage consistency model (multiple service instances, replicas/caches, and read routing) to rule out a stale-read-only explanation.
