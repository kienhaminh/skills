# Diagnosis — high confidence

The ingestion worker is not running. `pnpm dev` starts the server API and web application, but it does not start the separate pg-boss consumer. The submission endpoint successfully persists and enqueues the job, so it has an ID and remains in the queue; with no registered consumer, no ingestion pipeline work or worker log output can occur.

## Evidence

- The current root `dev` script is `turbo run dev`, and the server workspace's `dev` script starts Nest's default API entrypoint. Its distinct `dev:worker` script explicitly uses `--entryFile worker`.
- `apps/server/src/main.ts` boots `AppModule`; although that module includes the queue service, it only starts pg-boss and creates its queues. It registers no job handlers.
- `apps/server/src/worker.ts` is the only inspected entrypoint that calls `pgBoss.work(...)` for both `ingest.text` and `ingest.url`, then invokes the ingestion pipeline.
- The health endpoint only performs `SELECT 1` against Postgres and returns `{ status: "ok", db: "ok" }`; it does not assess worker presence, job consumption, or queue depth.
- The repository's debugging guide and README explicitly document this exact behavior: jobs submitted while only `pnpm dev` is running stay queued.

## Causal chain

`pnpm dev` → API accepts the ingestion request and `PgBossService.send(...)` creates a pg-boss job → no process has registered `work(...)` handlers → the job stays queued → neither document processing nor ingestion output occurs. A green `/health` response is compatible with this state because it verifies database reachability only.

## Alternatives considered

- **Failed enqueue:** unlikely and inconsistent with the returned job ID; the submission service throws when `send(...)` returns no job ID.
- **A failing ingestion pipeline or AI provider:** inconsistent with the queued state. Those paths are reached only from the worker handler, and failures there would occur after a consumer starts a job.
- **Database outage:** inconsistent with both the successful enqueue/status behavior and the reported health check, which verifies a database query.

## Remaining uncertainty

I did not inspect the live process list, service logs, or the specific `pgboss.job` row, so I cannot independently confirm that no worker was separately launched or rule out an unusual worker-to-database configuration mismatch. Given the stated startup command and the current checkout, the missing worker is the direct and documented cause with high confidence.
