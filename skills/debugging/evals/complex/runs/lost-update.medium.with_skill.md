# Diagnosis — lost update (high confidence, static analysis)

The counter uses an unprotected read–compute–write sequence. Two concurrent `increment` calls can both read the same value, each compute the same successor, and then overwrite one another with that successor. The final persisted value is therefore one higher rather than two higher.

## Facts checked

- `increment` reads the value, awaits the audit sink, calculates `current.value + 1`, then writes that absolute value.
- There is no transaction, compare-and-swap/version check, lock, or repository-level atomic increment in the service contract or call path inspected.
- The incident says the anomaly occurs only under concurrency; both audit events are present; no repository error is logged; and a later read returns the lower value.
- The fixture documents no known counter-consistency debt and directs read-only static analysis instead of load testing.

## Causal mechanism

For a stored value `N`, request A and request B can both finish `read` before either finishes `write`. Both retain `{ value: N }`. Each audit call completes and records an event, then each calculates `N + 1`. A writes `N + 1`; B subsequently writes the same `N + 1` (or vice versa). Both requests can report success, both audit events exist, and the durable counter ends at `N + 1`.

The `await` on `audit.observeIncrement` widens the interval in which the two requests can overlap, but it is not the root cause: any scheduling gap between the read and write permits the same stale-write race. The audit event is also not evidence of a committed increment because it occurs before the repository write and carries no value or transaction linkage.

## Alternatives considered

- **A repository write error:** inconsistent with two successful requests and no logged repository error, though the interface alone cannot prove the repository never suppresses failures.
- **A missing audit event or audit-only defect:** contradicted by the observation that both events exist; it also cannot explain the lower persisted value.
- **A stale/cached later read:** possible in an uninspected repository implementation, but it does not explain why the symptom is concurrency-specific as directly as the visible lost-update path. It could coexist with the primary race.
- **An external writer/decrement:** not supported by the inspected code or incident; confirming or excluding it needs database/audit correlation.

## Evidence still needed

Confirm the repository's actual storage semantics: emitted read/write values, request/correlation IDs, timestamps, transaction/version metadata, and the final database row for an affected pair. This should establish two reads of `N` followed by two writes of `N + 1`, and rule out a cached read, suppressed repository failure, or another writer. The exact backend implementation is also needed to verify whether it already provides an atomicity guarantee not represented by this interface.
