# Diagnosis: no ingestion worker was started

**Confidence: high.** The queued job is not being consumed because `pnpm dev` starts the Turbo `dev` task for workspace packages, whose current scripts start the server API and web application, but no worker process. The only registrations that drain `ingest.text` and `ingest.url` are in the separate `apps/server/src/worker.ts` entrypoint.

The submission succeeded because the API's `IngestionService` can write the submission and enqueue its pg-boss job. The job therefore remains a durable queued row until a consumer is running. The green `/health` result does not contradict this: its handler only executes `SELECT 1` through Drizzle and reports API/database reachability; it neither checks for a worker process nor queue consumption.

Evidence checked:

- Root `package.json` defines `dev` as `turbo run dev`; `apps/server/package.json` defines its `dev` script as the Nest API entrypoint and has a separate `dev:worker` script using `--entryFile worker`.
- `apps/server/src/worker.ts` is the sole observed location that calls `pgBoss.work(...)` for `ingest.text` and `ingest.url`.
- `apps/server/src/main.ts` boots `AppModule`, while `apps/server/src/worker.ts` boots the standalone `WorkerModule`; the API process does not register either job handler.
- `apps/server/src/health/health.controller.ts` performs only the database probe described above.
- `docs/DEBUG.md` independently documents this exact known behavior: `pnpm dev` does not start the ingestion worker and queued jobs wait in Postgres for a worker.

Causal chain: `pnpm dev` starts API/web only → submission endpoint enqueues a pg-boss job successfully → no process has registered the queue handlers → pg-boss leaves the job queued → no ingestion output appears. A database outage is unlikely because the request received a job ID and `/health` reports successful DB access. An enqueue failure is also unlikely because the API would throw rather than return normally when `PgBossService.send` returns no job ID.

Remaining uncertainty: no running process list, logs, or Postgres queue row was inspected, so this does not independently prove that a worker was absent at the exact incident time. It establishes that `pnpm dev` alone cannot start one in this checkout, and exactly explains the stated symptom.
