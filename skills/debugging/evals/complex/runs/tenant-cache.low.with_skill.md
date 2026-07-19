# Diagnosis: cache key omits tenant scope

**Confidence: high (static-code diagnosis; runtime confirmation still required).**

The most likely cause of the cross-tenant display-name anomaly is a shared cache key that is derived only from `userId`. `ProfileService.getProfile` receives both `tenantId` and `userId`, but constructs `profile:${userId}` before reading or writing the cache. A profile fetched for tenant A can therefore be stored under the same key later used by tenant B when both tenants share that user ID. On tenant B's request, a cache hit returns the already-cached tenant A `Profile` without calling the repository, so the repository's correct `(tenantId, userId)` query constraint cannot protect the response.

## Facts observed

- A `Profile` carries its `tenantId`, `userId`, and `displayName` (`src/profile.service.ts:1`).
- Repository lookup accepts both tenant and user identifiers (`src/profile.service.ts:3-5`) and is called with both (`src/profile.service.ts:19`).
- Cache operations accept only a pre-composed string key (`src/profile.service.ts:7-10`).
- The service composes that key as `profile:${userId}`, excluding `tenantId` (`src/profile.service.ts:15-17`), and stores the tenant-specific repository result under it (`src/profile.service.ts:19-20`).
- The incident states that all database queries include both identifiers, and reports require overlapping user IDs in two tenants on one long-lived process (`incident.md:3`).

## Causal mechanism

1. A request for `(tenant A, user X)` misses cache, retrieves A's profile with the correctly scoped repository call, and stores it at `profile:X`.
2. While that cache entry remains visible to the same long-lived process/cache namespace, a request for `(tenant B, user X)` reads `profile:X`.
3. The truthy cache hit returns A's complete profile directly (`src/profile.service.ts:17-18`), including A's display name; it bypasses the correctly scoped repository lookup.

This exactly accounts for the reported prerequisite of overlapping user IDs and why database traces remain correct. It also explains intermittency as cache-state/timing dependent: the symptom requires the other tenant's entry to be present when the conflicting request reads it. The report's long-lived-process condition is consistent with a cache whose entries persist across requests, but the concrete cache implementation and lifetime were not provided.

## Alternatives considered

- **Repository tenant filtering failure — unlikely.** The call site supplies both identifiers and the incident reports every traced database query does so. More importantly, the reported wrong response can occur on the cache-hit path, which makes no database request.
- **Concurrent cache write race — possible contributor, not necessary.** Concurrent misses can determine which tenant's profile is last stored under the shared key, but a sequential A-then-B request already produces the leak. Concurrency is not the root mechanism established by the code.
- **Cache implementation partitioning by an unshown tenant context — unresolved but unsupported.** The `Cache` interface receives only the user-derived key. An implementation could theoretically add implicit tenant isolation, but that would need external context not passed at this boundary; the incident's same-process condition instead fits a shared namespace.

## Evidence still needed

- The concrete cache implementation/configuration, including namespace, process scope, TTL, and whether it injects tenant isolation outside the key parameter.
- A non-mutating trace or cache inspection showing `profile:<overlapping-userId>` written for tenant A and read by tenant B without a repository call.
- Request/cache telemetry establishing whether entry expiry, eviction, or process restarts explains the observed frequency.
