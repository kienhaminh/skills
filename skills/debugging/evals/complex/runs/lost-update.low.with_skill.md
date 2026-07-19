# Diagnosis: lost update in counter increment (high confidence, static analysis)

The counter anomaly is most likely a classic lost-update race in `CounterService.increment`. The method performs a non-atomic read–modify–write sequence with no visible lock, transaction/compare-and-swap contract, or repository operation that increments at storage level. This is an analysis-derived conclusion because the incident is intentionally not reproducible locally and the repository implementation was not provided.

## Verified facts

- The incident reports that two successful concurrent requests can increase a counter by one rather than two; both audit events exist, no repository error is logged, and a later read observes the lower value.
- `increment` first reads the current value, then awaits audit observation, computes `current.value + 1`, and writes that computed value.
- `CounterRepository` exposes separate `read(id)` and unconditional `write(id, value)` operations. Its contract carries neither a version/precondition nor an atomic increment operation.
- The supplied debugging guidance says this requires production-level concurrency and directs read-only static analysis; the tech-debt record contains no previously acknowledged counter-consistency issue.

## Causal mechanism

For a counter at value `N`, two requests can both complete `read` before either completes `write`. Each request retains `N`, both can successfully await `observeIncrement`, and each then calculates `N + 1`. The first write stores `N + 1`; the second unconditional write stores the same `N + 1`, overwriting no different value but discarding the other logical increment. Both requests can therefore return successfully, both audit events can exist, no repository error is required, and the persisted later value is one increment short. The awaited audit call enlarges the interval between read and write, making this interleaving more likely, but it is not required for the race.

## Alternatives considered

- **Audit sink dropping an event:** inconsistent with the reported presence of both audit events and does not explain the lower persisted counter value.
- **Repository write failure or an unreported storage error:** possible in the abstract, but it fits the evidence less well because the incident reports successful requests and no repository error. It would also need an additional assumption about error swallowing or a false success.
- **A stale later read/cache:** could make the observed value appear low, but does not by itself explain why the issue occurs only under concurrency or why the service exposes an unsafe read–modify–write path. It remains a secondary possibility until storage/read-path behavior is checked.
- **Sequential duplicate/incorrect request handling:** does not fit the concurrency-only condition as directly as the interleaving above.

## Evidence still needed

- Repository implementation and database semantics: whether `read`/`write` share a transaction, whether writes are conditional/versioned, and whether an ORM/cache changes their behavior.
- Correlated production traces for two affected request IDs showing both reads of the same value followed by two writes of the same next value.
- Storage audit/history (or equivalent) proving the write order and persisted values, plus cache/read-path telemetry to rule out a stale later read.
- Confirmation that successful request responses are emitted only after `repo.write` resolves and that no outer retry, rollback, or compensating writer modifies this counter.
