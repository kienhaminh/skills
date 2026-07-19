# Diagnosis — high confidence

The incident is a contract-boundary mismatch, not a Postgres failure. `SearchResultEnricher.toSearchResult()` transforms an internal `SearchCandidate.excerptId` into the public `SearchResult.id`. The shared `SearchResult` contract defines `id`, not `excerptId`. Any production caller that subsequently reads `result.excerptId` is therefore reading a property that the declared and real result shape does not contain, so it receives `undefined`.

## Causal chain

- **Trigger:** A unit-test fake returned `{ excerptId, score }`, while the real enricher returned the public result shape `{ id, type, title, snippet, score, ... }`.
- **Broken assumption / root cause:** The test double was allowed to invent a different output contract from `SearchResultEnricher`, and a consumer assumed the internal candidate field name (`excerptId`) survived the enrichment boundary. The fake made that assumption look valid.
- **Symptom:** The unit test was green, but production reads of `excerptId` from enriched search results yielded `undefined`; a type-check flags the incompatible property access when the value is typed as `SearchResult`.

## Evidence

- `apps/server/src/knowledge/search-result-enricher.ts:29-44` declares `Promise<SearchResult>` and returns `id: candidate.excerptId`, not `excerptId`.
- `packages/contracts/src/knowledge-contracts.ts:28-42` defines the response item with required `id` and no `excerptId` field.
- `apps/server/src/knowledge/knowledge-search.service.ts:47-55` passes candidates through the enricher and returns those enriched items, so this is the boundary at which the field name changes.
- The integration setup constructs `KnowledgeSearchService` with the real `SearchResultEnricher` (`apps/server/src/int/knowledge-search.int-spec.ts:30-35`), whereas the reported unit-test fake bypassed that behavior.

The current checkout already reflects the correct fake shape in `apps/server/src/knowledge/knowledge-search.service.spec.ts:29-38`: it returns `id`, with an explicit comment documenting why. Also, `pnpm type-check` completed successfully in this checkout (from Turbo cache). Thus the reported bad fake and reported type error are not currently reproducible here; they describe the incident or a different revision.

## Why Postgres is not the cause

Postgres supplies raw candidate rows, whose id is deliberately stored as `SearchCandidate.excerptId` before enrichment. The failure occurs after that data has been received: the enricher maps it to the API/contract field `id`, and the consumer uses the pre-enrichment name. Neither database contents nor SQL result aliases can make a nonexistent `SearchResult.excerptId` property appear after this transformation.

## Remaining uncertainty

I did not find the specific production consumer described as reading `excerptId` in the current checkout, nor did I reproduce the stale test shape or type error because both appear already corrected. That prevents naming the exact historical caller or commit with certainty, but it does not materially weaken the contract-mismatch diagnosis given the stated incident and the verified producer/contract shapes.
