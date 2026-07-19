## Diagnosis

This is not a Postgres issue. The root cause is a broken contract between the search consumer and `SearchResultEnricher`: production results use `id`, while the consumer reads `excerptId`. The hand-written unit-test fake instead returned `excerptId`, so it modeled an obsolete or invented result shape and let the test pass despite the production incompatibility.

- **Trigger:** the enricher result shape changed or was supplied as `{ id, type, title, snippet, score }` at runtime.
- **Symptom:** production reads `result.excerptId` as `undefined`; type-checking reports that `excerptId` is absent from the real result type.
- **Root cause:** the fake and consumer were not checked against the real enricher contract, creating a false-green unit test.

Confidence: high. The reported runtime shape and compiler error directly account for the failure, whereas no stated evidence implicates query execution, database connectivity, or stored data.

Remaining uncertainty: the supplied facts do not establish when or where the contract drift originated (for example, a rename, an adapter bypass, or an incorrectly typed interface), nor whether any other consumers or mocks share the same stale assumption.
