# Diagnosis: search test was validating an invented mock contract, not Postgres

**Confidence: high.** The root cause was a contract mismatch at the unit-test collaborator boundary. The hand-written `SearchResultEnricher` fake returned `{ excerptId, score }`, while the real `SearchResultEnricher.toSearchResult()` returns a `SearchResult` whose identifier is `id` (with `type`, `title`, `snippet`, and `score`). Assertions that read `item.excerptId` therefore passed only because the mock supplied that non-production field. Production results have no `excerptId`, so the same read evaluates to `undefined`.

## Evidence

- `apps/server/src/knowledge/search-result-enricher.ts` constructs the runtime result with `id: candidate.excerptId`, and its declared return type is the shared `SearchResult` contract.
- `packages/contracts/src/knowledge-contracts.ts` defines `SearchResult` with required `id`, `type`, and `title`, optional `snippet` and `score`; it does not define `excerptId`.
- `apps/server/src/knowledge/knowledge-search.service.ts` passes candidates to the enricher and returns those enriched objects as `items`; it does not rename `id` to `excerptId` afterward.
- Commit `686f46a` documents this exact failure mode and changes the unit fake to mirror the real shape and the assertions to use `.id`. The current checkout reflects that correction.

## Causal chain

| Role | What happened |
| --- | --- |
| Trigger | A unit test used a hand-written fake with `{ excerptId, score }`. |
| Broken assumption / root cause | The fake was treated as interchangeable with `SearchResultEnricher` without preserving the collaborator's output contract. It created a field that runtime results never provide. |
| Symptom | The unit test was green while production consumers reading `excerptId` received `undefined`; TypeScript reported the incompatible property access once that check was visible. |

Postgres is not the cause on the observed path. It supplies candidate rows with `id`, which `KnowledgeSearchService` deliberately maps to the internal `SearchCandidate.excerptId`; the enricher then deliberately exposes that identifier as the public result field `id`. The divergence occurs after candidate retrieval, at the fake-versus-real result-shape boundary. No database behavior is needed to explain a property being present only in a mock and absent from the contract.

## Remaining uncertainty

I did not reproduce the historical broken revision or inspect the specific production consumer that read `excerptId`; the causal conclusion instead rests on the current runtime code, the shared contract, and the repository's targeted corrective commit. There may have been additional callers with the same incorrect expectation, but the evidence establishes the reported incident's cause and does not support a Postgres diagnosis.
