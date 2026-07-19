# Diagnosis

The cross-tenant display-name leak is caused by a tenant-agnostic in-process cache key in `ProfileService.getProfile`: it uses `profile:${userId}`. The repository lookup is correctly scoped with both `tenantId` and `userId`, so database traces remain correct. However, after one tenant's profile is cached, a later request from another tenant with the same `userId` reads that existing cache entry and returns it without calling the repository.

This explains why the issue occurs only when user IDs overlap across tenants and requests reach the same long-lived process: both conditions are needed for the first request's cached value to be available to the second tenant.

Confidence: high. The code directly proves that tenant scope is included at the repository boundary but omitted at the cache boundary, matching every stated incident condition. Runtime frequency is not established from static inspection, but it is not necessary to establish this failure path.
