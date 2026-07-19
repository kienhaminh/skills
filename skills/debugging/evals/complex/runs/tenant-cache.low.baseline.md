# Diagnosis: intermittent cross-tenant profile display

## Facts established from the fixture

- `ProfileRepository.find` accepts both `tenantId` and `userId`, and `ProfileService` passes both values to it.
- The cache key in `ProfileService.getProfile` is `profile:${userId}`; it does not include `tenantId`.
- On a cache hit, the service returns the cached `Profile` without checking that `cached.tenantId` equals the requested `tenantId`.
- The incident states that database traces always include both identifiers, while reports require overlapping user IDs in two tenants and a shared long-lived application process.

## Causal mechanism

The cache is shared across tenants at the key level. If tenant A requests user ID `U` after the entry is absent, the service stores A's profile under `profile:U`. A later request from tenant B for the same user ID reads that same key and returns A's profile before calling the repository. The returned profile can therefore carry A's display name (and tenant ID) for a request scoped to B.

This explains both the database evidence and the apparent intermittence: repository queries remain correctly tenant-scoped on cache misses, whereas the anomalous path is a cache hit. It depends on overlapping user IDs, a common cache/process lifetime, and request ordering or cache retention, so it will not occur consistently.

## Alternatives considered

- A repository query missing tenant filtering is not supported by the current service call or by the incident's database traces.
- A cross-tenant cache implementation failure is possible in principle, but is unnecessary to explain the behavior: the caller itself supplies a tenant-agnostic key and accepts any cached profile.
- Stale data within a single tenant could cause an outdated display name, but does not account for the incident's requirement of two tenants sharing a user ID or for the returned profile belonging to another tenant.

## Confidence

High confidence that the tenant-agnostic cache key, combined with no tenant validation on cache hits, is the direct code-level cause of the reported cross-tenant response. The source and incident conditions align exactly with this mechanism.

## Evidence still needed

- Confirmation that the injected `Cache` is shared by requests/tenants within the same long-lived process, rather than request-local.
- Cache telemetry or a safely captured trace showing a write for one tenant followed by a hit for the other tenant at `profile:<same-user-id>`.
- Confirmation of cache lifetime, eviction, and invalidation behavior to quantify why reports are occasional rather than universal.
- A runtime observation that the returned cached object's `tenantId` differs from the requested tenant during an affected request.
