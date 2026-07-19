# Diagnosis: tenant scope is absent from the cache key

`ProfileService.getProfile` reads and writes cache entries under `profile:${userId}`. That key does not include `tenantId`, although the repository lookup is correctly scoped by both `tenantId` and `userId`.

Consequently, on a long-lived process with a shared cache, a request for tenant A and user ID U can cache tenant A's profile. A later request for tenant B with the same user ID U resolves the identical cache key and returns the cached tenant A profile before `repo.find(tenantId, userId)` runs. This exactly accounts for another tenant's display name being shown while database traces still show fully scoped queries: the anomalous request does not reach the database.

Confidence: high. The cache-key collision is directly proven by the current code, and the incident conditions (overlapping user IDs and the same long-lived process) are the precise conditions needed for that collision to be observable. The rarity is a runtime frequency characteristic, but it does not weaken the code-level causal chain.
