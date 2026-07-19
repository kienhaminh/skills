# Diagnosis: cross-tenant profile cache collision (high confidence)

The most likely cause is that `ProfileService` caches profiles under `profile:${userId}` while the repository lookup is scoped by both `tenantId` and `userId`. Two tenants with the same user ID therefore address the same cache entry. A cached profile from one tenant can be returned to a request for the other tenant without another repository query.

This conclusion is derived from static code analysis; services and data were not started or changed.

## Verified facts

- The incident says the incorrect display name occurs only for overlapping user IDs, when requests use one long-lived application process.
- The incident says every database query includes both `tenantId` and `userId`.
- `ProfileService.getProfile` constructs the cache key solely from `userId`.
- On a cache hit, the method returns the cached `Profile` directly; it neither checks `cached.tenantId` against the request tenant nor calls the repository.
- On a miss, the repository result for a tenant is stored using that same user-only key.
- The documented debugging guidance specifically identifies two tenants with overlapping IDs and asks that tenant scope be traced across repository and cache boundaries. The tech-debt record lists no pre-existing tenant-isolation exception.

## Causal mechanism

1. A request for tenant A and user U misses `profile:U`, reads `(A, U)` from the correctly scoped repository, and stores it at `profile:U`.
2. A later request on the same shared cache for tenant B and user U reads `profile:U`.
3. The cache returns tenant A's `Profile`, including its display name. Because the hit path has no tenant validation, the service returns that profile as tenant B's result.

Either tenant can poison the shared key for the other. If entries expire, are evicted, or concurrent cold requests race to populate the key, the identity of the last stored profile can change; that makes the symptom intermittent and dependent on request order rather than on the database query.

## Alternatives considered

- **Repository query missing tenant scope:** contradicted by the incident's database traces and by the repository call receiving both identifiers. The repository implementation itself was not supplied, so this cannot be ruled out independently, but it is not needed to explain the symptom.
- **Incorrect display-name mapping after a correct profile is returned:** no such mapping exists in the supplied service. The direct cache return already explains why a complete profile from another tenant reaches the caller.
- **Cache is actually tenant-isolated outside this service:** possible only if the cache implementation implicitly partitions calls by request tenant despite receiving only the string key. That behavior is not evidenced by the supplied interface or code and would be inconsistent with the reported same-process condition.
- **A one-off stale database read:** does not explain the strong overlap-ID and same-long-lived-process conditions as directly as a shared user-only cache key.

## Remaining evidence needed

- Cache implementation and configuration: whether its namespace is process-wide, its eviction/TTL behavior, and whether it adds any hidden tenant partitioning.
- Cache telemetry or traces showing the same `profile:<userId>` key written by one tenant then read by another, with the stored `Profile.tenantId` different from the request tenant.
- Request correlation data to confirm the expected ordering around a reported incident, including concurrent cache misses where applicable.
- The repository implementation and an end-to-end response trace, to exclude an independent defect downstream of this service.

The causal chain is therefore high-confidence at the service boundary: overlapping tenant-local user IDs plus a shared long-lived cache lead to a user-only cache-key collision, after which the unchecked cache-hit path returns the other tenant's profile. Runtime cache evidence would confirm that this static mechanism occurred in each incident.
