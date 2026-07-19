# Diagnosis: queued ingestion job with green health

## Root cause

**High confidence:** the ingestion worker is not running. `pnpm dev` invokes Turbo's `dev` task for the web app and the server API only; it does not invoke the server's separate `dev:worker` script. The API successfully accepts the submission and enqueues an `ingest.text` or `ingest.url` pg-boss job, but only `apps/server/src/worker.ts` registers handlers that consume those queues. With that process absent, the job remains queued and no ingestion output is produced.

## Why green health does not contradict this

`/health` is served by the API process and checks only that its database query can run. It neither starts a worker nor checks that a worker is registered, alive, or draining pg-boss jobs. Therefore `{ status: "ok", db: "ok" }` is fully consistent with a queued ingestion job.

## Evidence from this checkout

- The root `dev` command is `turbo run dev`; the server's normal `dev` entrypoint is `nest start --watch`, whereas the worker is a separate `nest start --watch --entryFile worker` command.
- `apps/server/src/ingestion/ingestion.service.ts` returns a job ID only after calling `PgBossService.send(...)` for `ingest.text` or `ingest.url`.
- `apps/server/src/worker.ts` alone calls `pgBoss.work(...)` for those two job names.
- The repository README and debugging rules explicitly state that `pnpm dev` does not start the ingestion worker and that jobs remain queued until one is running.

## Remaining uncertainty

This conclusion explains the reported combination directly and is documented as an expected development-mode behavior. I did not inspect the live pg-boss table or process list, so I cannot independently confirm that no worker process was started separately, nor rule out a worker that started but failed before registering handlers. Those alternatives are less likely given the stated startup command and the exact queued-job symptom.
