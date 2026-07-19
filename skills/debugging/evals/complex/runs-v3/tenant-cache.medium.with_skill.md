Diagnosis (high confidence, analysis-derived): `ProfileService` caches profiles by `userId` alone (`profile:${userId}`), while repository lookup is scoped by both `tenantId` and `userId`. Once a long-lived process caches tenant A's profile for a shared user ID, a request from tenant B reads that same entry and returns A's display name without consulting the repository.

The violated invariant is that every profile cache entry must be isolated by the full tenant-and-user identity. The incident pattern directly matches this: it requires overlapping user IDs and a shared long-lived process; the database remains correctly tenant-scoped because the erroneous request is served from cache.

The strongest rejected alternative is a repository/query tenant-filter failure. Database traces show every query includes both identifiers, and the failure can occur before any query on a cache hit.

Remaining uncertainty is operational only: cache scope and eviction behavior are not shown. Confirm by tracing cache keys and hit/miss logs for two tenants sharing one user ID; a cross-tenant cache hit would conclusively verify the chain.
