# Diagnosis: cross-tenant profile cache collision

## Facts

- `ProfileRepository.find` accepts both `tenantId` and `userId`; the service passes both values to it.
- The cache key constructed by `ProfileService.getProfile` is `profile:${userId}`. It omits `tenantId`.
- On a cache hit, the service returns the cached `Profile` without checking that its `tenantId` matches the requested tenant.
- The incident is limited to tenants sharing a user ID on one long-lived process, while database traces remain tenant-scoped. Those conditions are consistent with a process-shared cache retaining a profile populated by a prior request.

## Causal mechanism

For tenant A and tenant B with the same `userId`, both requests use the same cache entry, `profile:<userId>`. If tenant A misses first, its tenant-A profile is fetched correctly from the repository and stored under that shared key. A later tenant-B request finds that entry and returns the tenant-A profile before issuing any database query. The returned display name can therefore belong to tenant A even though every database query includes the correct tenant ID.

This is intermittent because it depends on request ordering, cache lifetime/eviction, overlapping user IDs, and both requests reaching a process that shares the same cache state.

## Alternatives considered

- A repository query missing tenant scoping is not supported by the service call or by the reported database traces.
- Incorrect data persisted in the database is less consistent with the process-local and cross-tenant-ID preconditions; it would not inherently depend on cache residency or request order.
- A cache implementation defect remains possible, but it is not needed to explain the behavior: the service itself deliberately aliases profiles from different tenants to one key.

## Confidence

High. The cache-key collision and unvalidated cache-hit path are direct static-code evidence, and they match every reported incident condition.

## Evidence still needed

- Confirm whether the deployed cache is shared only within each application process or across processes, and its TTL/eviction behavior.
- Correlate affected requests with cache hit/miss logs and the cached profile's `tenantId` (without exposing profile data) to verify the proposed sequence in production.
- Establish whether any callers can request a profile with a user ID not unique within a tenant; that would affect the broader cache-key contract but does not change the identified tenant collision.
