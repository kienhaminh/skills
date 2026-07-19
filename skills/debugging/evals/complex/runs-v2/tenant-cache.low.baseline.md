## Diagnosis

The cross-tenant display-name leak is caused by the process-local cache key omitting `tenantId`. `ProfileService.getProfile()` reads and writes `profile:${userId}`, even though the repository lookup is correctly scoped by both `tenantId` and `userId`.

Consequently, if tenant A and tenant B share a user ID on the same long-lived process, a request for tenant A can cache A's profile under that user-only key. A later request for tenant B resolves the same key and returns A's cached profile before querying the database. This exactly accounts for the reports that database traces are tenant-correct, that the issue requires matching user IDs, and that it appears only when requests share a process.

Confidence: high. The failing isolation boundary is explicit in the only cache-key construction, and all reported conditions are necessary consequences of that key shape and cache lifetime.
