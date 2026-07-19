# Diagnosis: cache key omits tenant scope (high confidence)

The cross-tenant display-name anomaly is caused by `ProfileService` caching profiles under `profile:${userId}` rather than a key that includes `tenantId`. This makes the cache process-wide for a user ID even though the repository lookup is tenant-scoped.

Evidence from the current code:

- `repo.find(tenantId, userId)` receives both identifiers, matching the database traces in the incident report.
- The cache lookup and write both use only `profile:${userId}`.
- On a long-lived process, if tenant A requests user ID `U` first, the service stores tenant A's complete `Profile` at that shared key. A later request from tenant B for the same user ID obtains that cached object and returns it before calling the repository.

Causal chain: overlapping user IDs across tenants are the required trigger; the cache key's missing tenant discriminator is the broken isolation assumption; returning the prior cached `Profile` is the direct mechanism that exposes the other tenant's display name. The fact that reports require the same long-lived process is consistent with a retained in-memory or shared-process cache entry.

I reject an unscoped database query as the primary cause because the only repository call passes both `tenantId` and `userId`, and the incident's query traces independently show both predicates. A race is not required to explain the behavior: request order alone determines which tenant's profile occupies the shared key. Concurrent requests could affect frequency or which value wins, but are not the root cause.

Confidence is high for the code-level cause. This is static analysis, not a reproduction; the remaining runtime unknown is the cache's lifetime/scope, but the incident condition and the observed code are already sufficient to explain the leak if cache entries survive across the relevant requests.
