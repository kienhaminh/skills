# Diagnosis: lost update in the counter increment path (high confidence)

The counter is updated with a non-atomic read–modify–write sequence. Under concurrent requests, two invocations can both read the same stored value, compute the same next value, and then each write that identical value. The second write replaces the first with no error, so two successful increments leave the counter one higher rather than two higher.

## Evidence and causal chain

- **Verified fact:** The incident says the anomaly occurs only under concurrency; both audit events are present, no repository error is logged, and a later read shows the lower value.
- **Verified fact:** `CounterService.increment()` calls `repo.read(id)`, awaits the audit sink, calculates `current.value + 1`, and finally calls `repo.write(id, next)`. The repository contract exposes separate `read` and unconditional `write` operations; it expresses neither a transaction nor a compare-and-set/version precondition.
- **Inference:** For a stored value `N`, request A and request B can both finish `read` before either write. Each retains `N`, each computes `N + 1`, and each successfully writes `N + 1`. The persisted result is therefore `N + 1`; the last writer does not produce an error because it writes a valid value.
- **Inference:** The awaited audit call widens the interval between read and write, increasing the opportunity for the overlap, but it is not the root cause. Its two completed events are consistent with both requests reaching the increment workflow even though one persisted update is overwritten.

This chain accounts for every reported condition: concurrency is required for the overlap, both requests can succeed, both audit records can exist, the repository can log no error, and a later read can show the lower value.

## Alternatives considered

- An audit failure or missing audit event does not fit: the incident reports both events, and the audit call is awaited before the write.
- A repository write failure does not fit the reported successful requests and absence of repository errors. More importantly, ordinary write failure would not specifically produce a successful final value exactly one increment low.
- A stale later read is possible in systems with read replicas or caching, but no such mechanism appears in the inspected code or repository contract. It also does not explain why the anomaly is concurrency-specific as directly as the shared read–modify–write race.

## Confidence and remaining confirmation

Confidence is **high, but analysis-derived rather than runtime-confirmed**. The current code exposes the exact lost-update interleaving and the incident’s observations are its expected symptom. Confirmation would require production tracing or repository-level evidence showing two overlapping increments for the same ID both read the same value and subsequently write the same next value, plus confirmation that `CounterRepository.write` has no hidden atomic increment, transaction, or optimistic-concurrency behavior behind this interface.
