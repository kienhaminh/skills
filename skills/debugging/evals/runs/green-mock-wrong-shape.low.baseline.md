# Diagnosis: Green Mock, Wrong Runtime Result Shape

This is not evidence of a Postgres failure. The reported behavior is fully explained by an application-layer contract mismatch.

| Category | Finding |
| --- | --- |
| Trigger | The unit test replaces the real `SearchResultEnricher` with a hand-written fake returning `{ excerptId, score }`. |
| Symptom | Production receives real enriched results shaped as `{ id, type, title, snippet, score }`, then reads `excerptId`, which is `undefined`. The type checker reports the same mismatch. |
| Root cause | The consumer and its unit-test fake rely on an obsolete or incorrect result contract (`excerptId`) rather than the real enricher's contract (`id`, plus the other result fields). The test stays green because its fake reproduces the consumer's incorrect expectation instead of enforcing compatibility with the real interface. |

Confidence: high. The distinct result shapes, the undefined production field, and the type-check error all directly align with one contract-boundary failure. Postgres may supply underlying search data, but nothing in the incident indicates that it changes the object property names between the enricher and its consumer.

Remaining uncertainty: the supplied facts do not establish where the contract drift originated (for example, a rename, a stale type, or an incorrect adapter) or whether other consumers/fakes depend on the same obsolete field. They also do not establish whether the failure affects all search paths or only the path using this enricher.
