# Diagnosis: queued ingestion job with green health

## Root cause

**The ingestion worker was not started.**

`pnpm dev` runs Turbo's `dev` task. The server workspace defines that task as
`nest start --watch`, which boots `src/main.ts` (the HTTP API), and the web
workspace boots Next.js. It does not boot `src/worker.ts`.

The only code that registers pg-boss consumers for `ingest.text` and
`ingest.url` is `src/worker.ts`, where `PgBossService.work(...)` is called for
both queues. Without that separate process, a successfully submitted job
remains in pg-boss's queued state and no ingestion pipeline runs.

`GET /health` being green is consistent with this: its check only executes
`SELECT 1` through the API process's database connection. It does not check
for a live worker or an active pg-boss consumer.

## Confidence

High. The reported sequence matches the documented development behavior and
the entrypoints/wiring in the current checkout exactly: submission proves the
API can enqueue a pg-boss job; health proves the API can reach Postgres; neither
starts or verifies a queue consumer.

## Remaining uncertainty

This diagnosis assumes the observed job is genuinely in the queued state and
that no worker process was launched separately. The stated startup command
(`pnpm dev`) alone cannot launch one. If a separate worker was in fact running,
then its logs, environment/database target, and pg-boss job row would need
inspection to distinguish a disconnected or failed consumer from this cause.
