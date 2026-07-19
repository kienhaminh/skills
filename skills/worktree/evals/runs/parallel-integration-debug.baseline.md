# Concurrent integration-test and ingestion-debug plan

## Goal

Run the `apps/server` database integration suite concurrently in three feature worktrees while worktrees A and B independently reproduce and diagnose stuck ingestion jobs. Preserve each worktree’s data, queue state, ports, logs, and exit status so no result can be caused by another worktree truncating or consuming its jobs.

## Out of scope

- Creating or changing the three feature worktrees. Their absolute paths and branches must be supplied before execution.
- Editing application code, Jest configuration, `.env` files, timeouts, or tests.
- Adding monitoring dependencies or temporary logging.
- Using the root `pnpm test`; only `pnpm --filter server test:int` is meaningful here.
- Dropping databases, deleting Docker volumes, or using `docker compose down -v`.

## Current constraints

- Integration tests use real Postgres and real pg-boss, and are excluded from the unit suite: [docs/TESTING.md](/Users/kien.ha/Code/vietnam/docs/TESTING.md:24).
- Each Jest process runs suites serially with `maxWorkers: 1`, but the harness truncates shared application tables before tests: [jest.int.config.js](/Users/kien.ha/Code/vietnam/apps/server/jest.int.config.js:16), [db-harness.ts](/Users/kien.ha/Code/vietnam/apps/server/src/int/db-harness.ts:31).
- `TEST_DATABASE_URL` must name a database ending in `_test`: [db-harness.ts](/Users/kien.ha/Code/vietnam/apps/server/src/int/db-harness.ts:18).
- `pnpm dev` does not start the worker. A separate worker process is required: [docs/DEBUG.md](/Users/kien.ha/Code/vietnam/docs/DEBUG.md:33).
- API, worker, Drizzle, and pg-boss use the same `DATABASE_URL`; pg-boss therefore becomes isolated when the database is isolated: [pg-boss.service.ts](/Users/kien.ha/Code/vietnam/apps/server/src/queue/pg-boss.service.ts:8).
- Use `AI_PROVIDER=mock` first to remove network, cost, latency, and model nondeterminism: [docs/DEBUG.md](/Users/kien.ha/Code/vietnam/docs/DEBUG.md:28).
- Postgres is exposed on host port 5434. The compose default database is a known stale v2 name and must not be “fixed” during this run: [docker-compose.yml](/Users/kien.ha/Code/vietnam/docker-compose.yml:1), [tech-debt.md](/Users/kien.ha/Code/vietnam/docs/plans/tech-debt.md:27).

## Resource allocation

| Worktree | Integration database | Job-debug database | API port | Worker |
|---|---|---|---:|---|
| A | `vn_a_int_<tag>_test` | `vn_a_jobs_<tag>_test` | 8111 | A only |
| B | `vn_b_int_<tag>_test` | `vn_b_jobs_<tag>_test` | 8112 | B only |
| C | `vn_c_int_<tag>_test` | none | none | none |

All five databases may share the existing Postgres container. Database-level separation is sufficient because each database has its own application tables and `pgboss` schema. Never point a worker at an integration database: the test harness truncates document/submission/graph tables while tests run.

## 1. Establish paths and an evidence directory

Set the three real absolute worktree paths:

```bash
export REPO=/Users/kien.ha/Code/vietnam
export WT_A=/absolute/path/to/feature-a
export WT_B=/absolute/path/to/feature-b
export WT_C=/absolute/path/to/feature-c

export RUN_TAG=$(date -u +%Y%m%d%H%M%S)
export EVIDENCE=/tmp/vietnam-concurrency-${RUN_TAG}
mkdir -p "$EVIDENCE"

export DB_A_INT=vn_a_int_${RUN_TAG}_test
export DB_B_INT=vn_b_int_${RUN_TAG}_test
export DB_C_INT=vn_c_int_${RUN_TAG}_test
export DB_A_JOBS=vn_a_jobs_${RUN_TAG}_test
export DB_B_JOBS=vn_b_jobs_${RUN_TAG}_test

export URL_A_INT=postgresql://vft_user:vft_password@localhost:5434/${DB_A_INT}
export URL_B_INT=postgresql://vft_user:vft_password@localhost:5434/${DB_B_INT}
export URL_C_INT=postgresql://vft_user:vft_password@localhost:5434/${DB_C_INT}
export URL_A_JOBS=postgresql://vft_user:vft_password@localhost:5434/${DB_A_JOBS}
export URL_B_JOBS=postgresql://vft_user:vft_password@localhost:5434/${DB_B_JOBS}
```

Record provenance before running anything:

```bash
git -C "$REPO" worktree list --porcelain > "$EVIDENCE/worktrees.txt"

for wt in "$WT_A" "$WT_B" "$WT_C"; do
  test -d "$wt/.git" -o -f "$wt/.git" || {
    echo "Not a worktree: $wt" >&2
    exit 1
  }
done

{
  for wt in "$WT_A" "$WT_B" "$WT_C"; do
    echo "WORKTREE=$wt"
    git -C "$wt" status --short --branch
    git -C "$wt" rev-parse HEAD
    git -C "$wt" branch --show-current
    git -C "$wt" diff --stat
    shasum -a 256 "$wt/pnpm-lock.yaml"
  done
  node -v
  pnpm -v
} > "$EVIDENCE/provenance.txt"
```

Stop if any worktree path, branch, or SHA is not the intended feature branch. Dirty changes may remain, but they must be recorded and must not be edited by this procedure.

## 2. Verify the existing Postgres instance

```bash
docker compose -f "$REPO/docker-compose.yml" ps postgres \
  > "$EVIDENCE/postgres-compose-status.txt"

docker compose -f "$REPO/docker-compose.yml" exec -T postgres \
  pg_isready -U vft_user -d vietnamesetales \
  > "$EVIDENCE/postgres-readiness.txt"
```

Proceed only if `pg_isready` reports that it is accepting connections. Do not recreate the container or volume.

## 3. Provision and migrate isolated databases

This is an execution-time setup step; none of these commands should be run during plan review.

```bash
provision_db() {
  wt="$1"
  db="$2"
  url="$3"

  docker compose -f "$REPO/docker-compose.yml" exec -T postgres \
    createdb -U vft_user "$db"

  (
    cd "$wt" &&
    env DATABASE_URL="$url" pnpm --filter @vietnam/db db:init &&
    env DATABASE_URL="$url" pnpm --filter @vietnam/db db:migrate
  ) > "$EVIDENCE/migrate-${db}.log" 2>&1
}

provision_db "$WT_A" "$DB_A_INT"  "$URL_A_INT"
provision_db "$WT_B" "$DB_B_INT"  "$URL_B_INT"
provision_db "$WT_C" "$DB_C_INT"  "$URL_C_INT"
provision_db "$WT_A" "$DB_A_JOBS" "$URL_A_JOBS"
provision_db "$WT_B" "$DB_B_JOBS" "$URL_B_JOBS"
```

Verify database identity and extensions before any destructive test harness runs:

```bash
for db in "$DB_A_INT" "$DB_B_INT" "$DB_C_INT" "$DB_A_JOBS" "$DB_B_JOBS"; do
  docker compose -f "$REPO/docker-compose.yml" exec -T postgres \
    psql -X -U vft_user -d "$db" \
    -c "SELECT current_database(), extname FROM pg_extension WHERE extname IN ('vector','pg_trgm') ORDER BY extname;" \
    > "$EVIDENCE/verify-${db}.txt"
done
```

Each result must show its expected database plus both `pg_trgm` and `vector`.

## 4. Establish sequential integration-test baselines

A failure here is branch- or database-specific, not concurrency-specific.

```bash
(
  cd "$WT_A" &&
  env TEST_DATABASE_URL="$URL_A_INT" pnpm --filter server test:int
) > "$EVIDENCE/a-int-sequential.log" 2>&1
A_BASE_RC=$?

(
  cd "$WT_B" &&
  env TEST_DATABASE_URL="$URL_B_INT" pnpm --filter server test:int
) > "$EVIDENCE/b-int-sequential.log" 2>&1
B_BASE_RC=$?

(
  cd "$WT_C" &&
  env TEST_DATABASE_URL="$URL_C_INT" pnpm --filter server test:int
) > "$EVIDENCE/c-int-sequential.log" 2>&1
C_BASE_RC=$?

printf 'A=%s\nB=%s\nC=%s\n' \
  "$A_BASE_RC" "$B_BASE_RC" "$C_BASE_RC" \
  > "$EVIDENCE/sequential-exit-codes.txt"
```

Do not classify a later failure as concurrency-only unless the same worktree, SHA, database migration set, and test command pass here.

## 5. Prepare isolated ingestion-debug runtimes for A and B

Build the exact worktree code before starting stable, non-watch processes:

```bash
(
  cd "$WT_A" &&
  pnpm --filter @vietnam/db build &&
  pnpm --filter server build
) > "$EVIDENCE/a-build.log" 2>&1

(
  cd "$WT_B" &&
  pnpm --filter @vietnam/db build &&
  pnpm --filter server build
) > "$EVIDENCE/b-build.log" 2>&1
```

Use this local-only JWT value; it satisfies the required 32-character validation without exposing a real secret:

```bash
export DEBUG_JWT=local-debug-only-jwt-secret-00000001
```

Start each API and worker against only its job-debug database:

```bash
(
  cd "$WT_A" &&
  env NODE_ENV=development \
      PORT=8111 \
      DATABASE_URL="$URL_A_JOBS" \
      AI_PROVIDER=mock \
      JWT_SECRET="$DEBUG_JWT" \
      INGESTION_ALLOW_PRIVATE_URLS=false \
      pnpm --filter server start:api
) > "$EVIDENCE/a-api.log" 2>&1 &
A_API_PID=$!

(
  cd "$WT_A" &&
  env NODE_ENV=development \
      DATABASE_URL="$URL_A_JOBS" \
      AI_PROVIDER=mock \
      JWT_SECRET="$DEBUG_JWT" \
      INGESTION_ALLOW_PRIVATE_URLS=false \
      pnpm --filter server start:worker
) > "$EVIDENCE/a-worker.log" 2>&1 &
A_WORKER_PID=$!

(
  cd "$WT_B" &&
  env NODE_ENV=development \
      PORT=8112 \
      DATABASE_URL="$URL_B_JOBS" \
      AI_PROVIDER=mock \
      JWT_SECRET="$DEBUG_JWT" \
      INGESTION_ALLOW_PRIVATE_URLS=false \
      pnpm --filter server start:api
) > "$EVIDENCE/b-api.log" 2>&1 &
B_API_PID=$!

(
  cd "$WT_B" &&
  env NODE_ENV=development \
      DATABASE_URL="$URL_B_JOBS" \
      AI_PROVIDER=mock \
      JWT_SECRET="$DEBUG_JWT" \
      INGESTION_ALLOW_PRIVATE_URLS=false \
      pnpm --filter server start:worker
) > "$EVIDENCE/b-worker.log" 2>&1 &
B_WORKER_PID=$!

printf 'A_API=%s\nA_WORKER=%s\nB_API=%s\nB_WORKER=%s\n' \
  "$A_API_PID" "$A_WORKER_PID" "$B_API_PID" "$B_WORKER_PID" \
  > "$EVIDENCE/runtime-pids.txt"
```

Confirm API/database readiness and worker registration:

```bash
curl -fsS http://localhost:8111/health > "$EVIDENCE/a-health.json"
curl -fsS http://localhost:8112/health > "$EVIDENCE/b-health.json"

rg -n "worker started|pg-boss error|Invalid environment" \
  "$EVIDENCE/a-worker.log" "$EVIDENCE/b-worker.log" \
  > "$EVIDENCE/worker-readiness.txt"
```

Both worker logs must contain `worker started — listening for ingest.text / ingest.url jobs`. Merely having an API process is not evidence that jobs can drain.

If reproducing through HTTP, create one worktree-local API key per job database. Capture the displayed plaintext interactively and never redirect it into evidence:

```bash
(
  cd "$WT_A" &&
  env DATABASE_URL="$URL_A_JOBS" \
      AI_PROVIDER=mock \
      JWT_SECRET="$DEBUG_JWT" \
      pnpm --filter server create-api-key -- \
      --name wt-a-debug \
      --scopes kb:read,kb:write
)

(
  cd "$WT_B" &&
  env DATABASE_URL="$URL_B_JOBS" \
      AI_PROVIDER=mock \
      JWT_SECRET="$DEBUG_JWT" \
      pnpm --filter server create-api-key -- \
      --name wt-b-debug \
      --scopes kb:read,kb:write
)

read -s DEBUG_API_KEY_A
export DEBUG_API_KEY_A
read -s DEBUG_API_KEY_B
export DEBUG_API_KEY_B
```

Submit the exact reported payload—not a simplified substitute—and save only the JSON response. For a text-ingestion reproduction:

```bash
curl -fsS \
  -H "Authorization: Bearer ${DEBUG_API_KEY_A}" \
  -H "Content-Type: application/json" \
  -d '{"content":"<exact A reproduction text>","sourceDescription":"concurrency reproduction A"}' \
  http://localhost:8111/v1/contributions \
  > "$EVIDENCE/a-submit.json"

curl -fsS \
  -H "Authorization: Bearer ${DEBUG_API_KEY_B}" \
  -H "Content-Type: application/json" \
  -d '{"content":"<exact B reproduction text>","sourceDescription":"concurrency reproduction B"}' \
  http://localhost:8112/v1/contributions \
  > "$EVIDENCE/b-submit.json"
```

Keep `INGESTION_ALLOW_PRIVATE_URLS=false`. Set it to `true` only for a deliberately local URL fixture on a private machine; it disables the SSRF guard.

## 6. Capture the stuck-job state before the concurrent test run

For each debug database:

```bash
snapshot_jobs() {
  db="$1"
  output="$2"

  docker compose -f "$REPO/docker-compose.yml" exec -T postgres \
    psql -X -U vft_user -d "$db" -c "
      SELECT
        clock_timestamp() AS observed_at,
        id,
        name,
        state,
        retry_count,
        retry_limit,
        created_on,
        start_after,
        started_on,
        completed_on,
        expire_in,
        output,
        data
      FROM pgboss.job
      WHERE name IN ('ingest.text','ingest.url')
      ORDER BY created_on, id;
    " > "$output"
}

snapshot_jobs "$DB_A_JOBS" "$EVIDENCE/a-jobs-before.txt"
snapshot_jobs "$DB_B_JOBS" "$EVIDENCE/b-jobs-before.txt"
```

Also capture application-row existence for every job payload:

```bash
docker compose -f "$REPO/docker-compose.yml" exec -T postgres \
  psql -X -U vft_user -d "$DB_A_JOBS" -c "
    SELECT j.id AS job_id, j.state, j.data,
           d.id AS document_id, d.submission_id,
           e.id AS excerpt_id
    FROM pgboss.job j
    LEFT JOIN documents d ON d.id = NULLIF(j.data->>'documentId','')::uuid
    LEFT JOIN excerpts e ON e.document_id = d.id
    WHERE j.name IN ('ingest.text','ingest.url')
    ORDER BY j.created_on, e.span_start;
  " > "$EVIDENCE/a-job-chain-before.txt"

docker compose -f "$REPO/docker-compose.yml" exec -T postgres \
  psql -X -U vft_user -d "$DB_B_JOBS" -c "
    SELECT j.id AS job_id, j.state, j.data,
           d.id AS document_id, d.submission_id,
           e.id AS excerpt_id
    FROM pgboss.job j
    LEFT JOIN documents d ON d.id = NULLIF(j.data->>'documentId','')::uuid
    LEFT JOIN excerpts e ON e.document_id = d.id
    WHERE j.name IN ('ingest.text','ingest.url')
    ORDER BY j.created_on, e.span_start;
  " > "$EVIDENCE/b-job-chain-before.txt"
```

For URL jobs, also inspect `submissionId` and `sourceId` from `data`, because the document may correctly not exist until the worker materializes it.

## 7. Launch the three integration suites concurrently

Start all three from one controlling shell so their start times and exit codes are comparable:

```bash
(
  cd "$WT_A" &&
  env TEST_DATABASE_URL="$URL_A_INT" pnpm --filter server test:int
) > "$EVIDENCE/a-int-concurrent.log" 2>&1 &
A_INT_PID=$!

(
  cd "$WT_B" &&
  env TEST_DATABASE_URL="$URL_B_INT" pnpm --filter server test:int
) > "$EVIDENCE/b-int-concurrent.log" 2>&1 &
B_INT_PID=$!

(
  cd "$WT_C" &&
  env TEST_DATABASE_URL="$URL_C_INT" pnpm --filter server test:int
) > "$EVIDENCE/c-int-concurrent.log" 2>&1 &
C_INT_PID=$!

printf '%s concurrent tests started A=%s B=%s C=%s\n' \
  "$(date -u +%FT%TZ)" "$A_INT_PID" "$B_INT_PID" "$C_INT_PID" \
  > "$EVIDENCE/concurrent-start.txt"
```

While they run, capture shared-instance pressure and blocking every two seconds:

```bash
(
  while kill -0 "$A_INT_PID" 2>/dev/null ||
        kill -0 "$B_INT_PID" 2>/dev/null ||
        kill -0 "$C_INT_PID" 2>/dev/null; do
    date -u +%FT%TZ

    docker compose -f "$REPO/docker-compose.yml" exec -T postgres \
      psql -X -U vft_user -d postgres -c "
        SELECT datname, numbackends, xact_commit, xact_rollback,
               deadlocks, temp_files, temp_bytes,
               blk_read_time, blk_write_time
        FROM pg_stat_database
        WHERE datname IN (
          '$DB_A_INT','$DB_B_INT','$DB_C_INT',
          '$DB_A_JOBS','$DB_B_JOBS'
        )
        ORDER BY datname;

        SELECT pid, datname, application_name, state,
               wait_event_type, wait_event,
               clock_timestamp() - query_start AS query_age,
               left(query, 240) AS query
        FROM pg_stat_activity
        WHERE datname IN (
          '$DB_A_INT','$DB_B_INT','$DB_C_INT',
          '$DB_A_JOBS','$DB_B_JOBS'
        )
        ORDER BY datname, pid;

        SELECT blocked.pid AS blocked_pid,
               blocked.datname AS blocked_db,
               blocker.pid AS blocker_pid,
               blocker.datname AS blocker_db,
               blocked.wait_event_type,
               blocked.wait_event
        FROM pg_stat_activity blocked
        JOIN pg_locks blocked_lock
          ON blocked_lock.pid = blocked.pid
         AND NOT blocked_lock.granted
        JOIN pg_locks blocker_lock
          ON blocker_lock.locktype = blocked_lock.locktype
         AND blocker_lock.database IS NOT DISTINCT FROM blocked_lock.database
         AND blocker_lock.relation IS NOT DISTINCT FROM blocked_lock.relation
         AND blocker_lock.page IS NOT DISTINCT FROM blocked_lock.page
         AND blocker_lock.tuple IS NOT DISTINCT FROM blocked_lock.tuple
         AND blocker_lock.transactionid IS NOT DISTINCT FROM blocked_lock.transactionid
         AND blocker_lock.classid IS NOT DISTINCT FROM blocked_lock.classid
         AND blocker_lock.objid IS NOT DISTINCT FROM blocked_lock.objid
         AND blocker_lock.objsubid IS NOT DISTINCT FROM blocked_lock.objsubid
         AND blocker_lock.granted
        JOIN pg_stat_activity blocker ON blocker.pid = blocker_lock.pid;
      "
    sleep 2
  done
) > "$EVIDENCE/postgres-concurrency-samples.txt" 2>&1 &
PG_MONITOR_PID=$!
```

Collect results:

```bash
wait "$A_INT_PID"; A_INT_RC=$?
wait "$B_INT_PID"; B_INT_RC=$?
wait "$C_INT_PID"; C_INT_RC=$?
wait "$PG_MONITOR_PID"

printf 'A=%s\nB=%s\nC=%s\n' \
  "$A_INT_RC" "$B_INT_RC" "$C_INT_RC" \
  > "$EVIDENCE/concurrent-exit-codes.txt"

snapshot_jobs "$DB_A_JOBS" "$EVIDENCE/a-jobs-after.txt"
snapshot_jobs "$DB_B_JOBS" "$EVIDENCE/b-jobs-after.txt"

cp "$EVIDENCE/a-worker.log" "$EVIDENCE/a-worker-final.log"
cp "$EVIDENCE/b-worker.log" "$EVIDENCE/b-worker-final.log"
```

## 8. Diagnose failures using Frame → Observe → Model → Hypothesize → Test → Conclude

### Frame

For each failure, record:

- Worktree, branch, SHA, test suite, exact failing assertion, and elapsed time.
- Whether the same SHA passed sequentially.
- Which debug job ID was active at the same time.
- Expected state transition and the first timestamp at which it stopped progressing.

### Observe

Use the evidence to classify the first divergence:

- `created` with `start_after <= now()` plus no worker-ready log: missing or failed worker startup.
- `created` with a ready worker: verify the worker and job are using the same database and queue name.
- `retry` with future `start_after`: scheduled exponential backoff, not necessarily stuck.
- `active` with `started_on + expire_in < now()`: expired handler or pg-boss maintenance failure.
- `failed`: treat `output` and the worker’s matching timestamp as the primary failure evidence.
- Submission/document exists but no pg-boss row: inspect the enqueue boundary. The application commits its write transaction before enqueueing, so an orphaned submission is possible: [ingestion.service.ts](/Users/kien.ha/Code/vietnam/apps/server/src/ingestion/ingestion.service.ts:92).
- Job row exists but its referenced document does not: distinguish wrong-database execution from deletion/truncation.
- Excerpts exist while the job retries: inspect chunk idempotency before claiming duplication.
- A job missing from `pgboss.job`: check `pgboss.archive`; the API status method intentionally reads only the live table: [ingestion.service.ts](/Users/kien.ha/Code/vietnam/apps/server/src/ingestion/ingestion.service.ts:199).

### Model

Trace each job through:

```text
API submission transaction
  -> source/submission/document commit
  -> pg-boss send
  -> pgboss.job state
  -> worker subscription
  -> document lookup/materialization
  -> chunk extraction
  -> excerpt/claim/entity transaction
  -> embedding
  -> completed/failed/retry
```

A and B must never share any node in that chain except the physical Postgres server.

### Distinguishing tests

1. Re-run only the failed suite alone against the same isolated database:

```bash
(
  cd "$WT_A" &&
  env TEST_DATABASE_URL="$URL_A_INT" \
    pnpm --filter server test:int -- ingestion-pipeline.int-spec.ts
) > "$EVIDENCE/a-failed-suite-alone.log" 2>&1
```

Replace the filename with the actual failing suite and repeat for the affected worktree.

2. Re-run pairwise concurrency: A+B, A+C, then B+C. Use the same launch pattern and isolated URLs. This identifies whether one branch/process combination is necessary.

3. Repeat the minimal failing combination five times, preserving one log per iteration:

```bash
for attempt in 1 2 3 4 5; do
  (
    cd "$WT_A" &&
    env TEST_DATABASE_URL="$URL_A_INT" \
      pnpm --filter server test:int -- ingestion-pipeline.int-spec.ts
  ) > "$EVIDENCE/a-attempt-${attempt}.log" 2>&1 &
  PID_A=$!

  (
    cd "$WT_B" &&
    env TEST_DATABASE_URL="$URL_B_INT" \
      pnpm --filter server test:int -- ingestion-pipeline.int-spec.ts
  ) > "$EVIDENCE/b-attempt-${attempt}.log" 2>&1 &
  PID_B=$!

  wait "$PID_A"; RC_A=$?
  wait "$PID_B"; RC_B=$?
  printf '%s A=%s B=%s\n' "$attempt" "$RC_A" "$RC_B" \
    >> "$EVIDENCE/repeat-exit-codes.txt"
done
```

4. Interpret outcomes:

- Fails sequentially: branch/schema/test defect, not concurrency.
- Passes sequentially but fails with isolated databases and Postgres waits or timeouts: shared-instance capacity, lock, connection, CPU, or I/O contention.
- Cross-database blocking appears: inspect the recorded lock type; ordinary table locks cannot cross databases, so global objects, connection exhaustion, or host pressure become stronger hypotheses.
- Failure disappears when ingestion runtimes are stopped but remains in the same three test processes: interaction with API/worker connection or host load.
- Failure follows one branch through pairwise runs: branch-specific code or migration.
- Failure follows one database after recreating and remigrating it from the same branch: migration/database-state issue.
- Jobs move only when the worker starts: missing-worker trigger confirmed.
- Jobs remain `created` despite the ready marker: verify `current_database()`, queue names, and worker startup errors before changing code.

### Conclude

For each finding, write:

- Confidence: high, medium, or low.
- Trigger.
- Broken assumption or mechanism.
- Downstream symptom.
- Evidence filenames and timestamps.
- Rejected alternatives and why.
- Exact remaining uncertainty.

Do not propose or implement a fix during this diagnostic run.

## 9. Verification and shutdown

The run is complete when:

- All three sequential baselines and concurrent exit codes are recorded.
- Every integration process used a distinct `_test` database.
- A/B worker logs contain readiness markers and job identifiers.
- Queue snapshots exist before and after the concurrent interval.
- Postgres activity/lock samples span the failure interval.
- No `.env`, test, timeout, or source file was edited.
- `git status --short` after the run matches the recorded pre-run status, apart from explicitly understood generated build artifacts.

Capture final status:

```bash
for wt in "$WT_A" "$WT_B" "$WT_C"; do
  {
    echo "WORKTREE=$wt"
    git -C "$wt" status --short --branch
    git -C "$wt" rev-parse HEAD
  } >> "$EVIDENCE/final-worktree-state.txt"
done
```

Stop APIs and workers with `SIGINT` so Nest shutdown hooks call `PgBossService.stop()`:

```bash
kill -INT "$A_API_PID" "$A_WORKER_PID" "$B_API_PID" "$B_WORKER_PID"
wait "$A_API_PID" "$A_WORKER_PID" "$B_API_PID" "$B_WORKER_PID"
```

Retain the five databases until the evidence has been reviewed. Dropping them is a separate destructive cleanup step requiring explicit approval.

<oai-mem-citation>
<citation_entries>
MEMORY.md:1-3|note=[used repo guidance to defer debugging procedure to current local docs and code]
</citation_entries>
<rollout_ids>
019f70f3-9089-7231-bb94-5118f5ddd93b
</rollout_ids>
</oai-mem-citation>
