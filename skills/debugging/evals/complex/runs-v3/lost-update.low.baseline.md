## Diagnosis

This is a lost-update race in `CounterService.increment`.

Each request reads the counter, independently computes `current.value + 1`, then writes that value. Under concurrency, two requests can both read the same old value before either write completes. They will each emit an audit event and both successfully write the same next value, so the persisted counter rises by one rather than two. The later read therefore shows the lower value, and no repository error is expected.

Confidence: high. The incident pattern exactly matches the unprotected read–modify–write sequence in the current code, and the code has no visible atomic increment, transaction/lock, version check, or compare-and-swap behavior.

To confirm, capture the two overlapping requests' read values and write values (or database query traces). Confirmation would show both reads returning the same value and both writes persisting that same incremented value.
