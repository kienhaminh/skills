# Diagnosis: concurrent lost update

## Facts

- `CounterService.increment()` reads the counter, emits an audit event, derives `current.value + 1`, and writes that derived value in separate awaited operations (`src/counter.service.ts:14-17`). The repository contract exposes only independent `read` and `write` methods (`src/counter.service.ts:1-4`); no transaction, conditional write, lock, or atomic increment is visible in this service or contract.
- The incident reports that the anomaly occurs only with concurrency: two successful requests result in a net increment of one, both audit events exist, neither request logs a repository error, and a later read shows the lower value (`incident.md:3`).
- The repository documentation places current code above debugging guidance and the incident in the trust order (`docs/README.md:1-3`). The debugging guidance explicitly requires read-only analysis and distinguishes facts from hypotheses (`docs/DEBUG.md:1-3`).

## Most likely causal mechanism

This is most consistent with a lost-update race. For a starting value `N`, two concurrent calls can both complete `read(id)` before either completes `write(id, ...)`. Each then calculates `N + 1`; both writes succeed, and the later write stores the same `N + 1` value rather than a value based on the other request's update. Consequently, both requests can return success and both audit observations can persist while the final counter advances by only one.

The `await audit.observeIncrement(id)` between the read and write increases the interval in which a second request can read the same old value, but it is not itself shown to cause the data loss. The defining issue is that the value used for the write is a stale snapshot and the write has no visible compare-and-set or serialization guarantee.

## Alternatives and limits

- A repository implementation might silently apply last-write-wins semantics, or might use a cache/replica such that the later read is stale. Either could produce the reported final value, but neither behavior is visible from the interface alone.
- A duplicate-request/idempotency defect could explain two audit events, but it would not by itself explain why two independently successful increments collapse to one; the exposed read/write sequence explains that symptom directly.
- The audit sink could be durable independently of counter storage, which would explain the audit/counter divergence. Its implementation and failure semantics are not available, so the exact ordering and durability guarantees are unknown.
- No claim can be made from this source about the database isolation level, cross-process locking, retry behavior, or whether callers target the same `id`.

## Confidence

High confidence that the service contains a lost-update vulnerability under concurrent increments for the same counter. Medium confidence that it is the observed production mechanism, because the repository and audit implementations plus production traces have not been inspected.

## Evidence needed to confirm

1. Correlated production traces for two affected requests: counter ID, read value and time, write value and time, request outcome, and audit-event IDs. Confirmation would show both requests reading the same pre-update value and both writing the same successor value.
2. The concrete repository implementation and its datastore queries, including transaction/isolation, conditional-update, locking, retry, cache, and replica behavior. This determines whether the service-level interleaving can reach storage unchanged.
3. Audit-sink persistence and ordering records for the same request IDs, to establish why two audit events remain when only one logical state change survives.
4. Request routing evidence that the affected calls target the same `id` and do not involve retries or duplicate delivery that changes the interpretation.
