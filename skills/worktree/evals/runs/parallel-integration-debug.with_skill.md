# Read-only execution plan

## Goal and topology

Run three feature worktrees concurrently against one existing PostgreSQL container, while worktrees A and B independently reproduce and diagnose ingestion jobs. The current root checkout is `dev@9b75e054422c` and has unrelated modified documentation; leave it untouched.

| Slot | Worktree / branch | Integration DB | Ingestion-debug DB | Reserved API/web |
|---|---|---|---|---|
| A | `/Users/kien.ha/Code/vietnam-feature-a` / `codex/feature-a` | `vietnam_v3_fa_test` | `vietnam_v3_fa_ingestion_test` | 8110 / 3110 |
| B | `/Users/kien.ha/Code/vietnam-feature-b` / `codex/feature-b` | `vietnam_v3_fb_test` | `vietnam_v3_fb_ingestion_test` | 8210 / 3210 |
| C | `/Users/kien.ha/Code/vietnam-feature-c` / `codex/feature-c` | `vietnam_v3_fc_test` | none | 8310 / 3310 |

Assign one owner to each worktree. Dependencies, Jest caches, logs, environment, branch, and database are worktree-specific. Share only pnpm’s content-addressed store and one PostgreSQL service.

Do not launch multiple Compose projects: `docker-compose.yml` fixes `container_name: vft-postgres`, host port `5434`, and a named volume, so `docker compose -p` cannot isolate it.

## Provisioning commands

First inventory and confirm that the proposed branches and sibling paths are unused:

```bash
git -C /Users/kien.ha/Code/vietnam status --short --branch
git -C /Users/kien.ha/Code/vietnam worktree list --porcelain
git -C /Users/kien.ha/Code/vietnam branch -vv
python3 /Users/kien.ha/Code/vietnam/.codex/skills/worktree/scripts/worktree_matrix.py inventory \
  --repo /Users/kien.ha/Code/vietnam
```

After explicit authorization, create from the committed base, not the dirty working tree:

```bash
git -C /Users/kien.ha/Code/vietnam worktree add -b codex/feature-a \
  /Users/kien.ha/Code/vietnam-feature-a 9b75e054422c3e20ddf27c1a5bf73e5fda82b9c6
git -C /Users/kien.ha/Code/vietnam worktree add -b codex/feature-b \
  /Users/kien.ha/Code/vietnam-feature-b 9b75e054422c3e20ddf27c1a5bf73e5fda82b9c6
git -C /Users/kien.ha/Code/vietnam worktree add -b codex/feature-c \
  /Users/kien.ha/Code/vietnam-feature-c 9b75e054422c3e20ddf27c1a5bf73e5fda82b9c6

pnpm --dir /Users/kien.ha/Code/vietnam-feature-a install --frozen-lockfile
pnpm --dir /Users/kien.ha/Code/vietnam-feature-b install --frozen-lockfile
pnpm --dir /Users/kien.ha/Code/vietnam-feature-c install --frozen-lockfile
```

Start PostgreSQL once from the coordinator checkout. Before creation, query `pg_database`; if any allocated name exists, stop and choose new names rather than reusing or dropping unknown data.

```bash
docker compose -f /Users/kien.ha/Code/vietnam/docker-compose.yml up -d postgres
docker compose -f /Users/kien.ha/Code/vietnam/docker-compose.yml exec -T postgres \
  psql -U vft_user -d postgres -Atc \
  "SELECT datname FROM pg_database WHERE datname IN ('vietnam_v3_fa_test','vietnam_v3_fa_ingestion_test','vietnam_v3_fb_test','vietnam_v3_fb_ingestion_test','vietnam_v3_fc_test');"
```

For each allocation, create the database, then run `db:init` and `db:migrate` from its owning worktree. Example template:

```bash
docker compose -f /Users/kien.ha/Code/vietnam/docker-compose.yml exec -T postgres \
  createdb -U vft_user DB_NAME
DATABASE_URL=postgresql://vft_user:vft_password@localhost:5434/DB_NAME \
  pnpm --dir WORKTREE --filter @vietnam/db db:init
DATABASE_URL=postgresql://vft_user:vft_password@localhost:5434/DB_NAME \
  pnpm --dir WORKTREE --filter @vietnam/db db:migrate
```

Apply it to A’s two databases from A, B’s two from B, and C’s database from C. Every integration-test database preserves the harness-required `_test` suffix.

## Evidence and concurrent execution

```bash
export VT_EVIDENCE
VT_EVIDENCE=$(mktemp -d /private/tmp/vietnam-worktrees.XXXXXX)
mkdir -p "$VT_EVIDENCE"/{jest,seed,workers,int,solo,sql}
```

Seed one valid queued text-ingestion job in each debug database without starting an API or using external AI:

```bash
python3 /Users/kien.ha/Code/vietnam/.codex/skills/worktree/scripts/worktree_matrix.py run \
  --repo /Users/kien.ha/Code/vietnam \
  --worktree /Users/kien.ha/Code/vietnam-feature-a \
  --worktree /Users/kien.ha/Code/vietnam-feature-b \
  --max-parallel 2 --log-dir "$VT_EVIDENCE/seed" -- zsh -lc '
case "$WORKTREE_SLOT" in
  0) db=vietnam_v3_fa_ingestion_test ;;
  1) db=vietnam_v3_fb_ingestion_test ;;
esac
exec env TEST_DATABASE_URL="postgresql://vft_user:vft_password@localhost:5434/$db" \
  pnpm --filter server test:int \
  --cacheDirectory="$VT_EVIDENCE/jest/seed-$WORKTREE_NAME" \
  ingestion.service.int-spec.ts \
  -t "actually lands a job row in pgboss.job for the worker to pick up"
'
```

In a dedicated terminal, start only A and B workers. `AI_PROVIDER=mock` removes network, cost, and LLM nondeterminism:

```bash
python3 /Users/kien.ha/Code/vietnam/.codex/skills/worktree/scripts/worktree_matrix.py run \
  --repo /Users/kien.ha/Code/vietnam \
  --worktree /Users/kien.ha/Code/vietnam-feature-a \
  --worktree /Users/kien.ha/Code/vietnam-feature-b \
  --max-parallel 2 --log-dir "$VT_EVIDENCE/workers" -- zsh -lc '
case "$WORKTREE_SLOT" in
  0) db=vietnam_v3_fa_ingestion_test ;;
  1) db=vietnam_v3_fb_ingestion_test ;;
esac
exec env NODE_ENV=development \
  DATABASE_URL="postgresql://vft_user:vft_password@localhost:5434/$db" \
  AI_PROVIDER=mock INGESTION_ALLOW_PRIVATE_URLS=false \
  JWT_SECRET=local-debug-only-0123456789abcdef \
  pnpm --filter server dev:worker
'
```

After both logs contain `worker started`, launch all integration suites concurrently in another terminal:

```bash
python3 /Users/kien.ha/Code/vietnam/.codex/skills/worktree/scripts/worktree_matrix.py run \
  --repo /Users/kien.ha/Code/vietnam \
  --worktree /Users/kien.ha/Code/vietnam-feature-a \
  --worktree /Users/kien.ha/Code/vietnam-feature-b \
  --worktree /Users/kien.ha/Code/vietnam-feature-c \
  --max-parallel 3 --log-dir "$VT_EVIDENCE/int" -- zsh -lc '
case "$WORKTREE_SLOT" in
  0) db=vietnam_v3_fa_test ;;
  1) db=vietnam_v3_fb_test ;;
  2) db=vietnam_v3_fc_test ;;
esac
exec env TEST_DATABASE_URL="postgresql://vft_user:vft_password@localhost:5434/$db" \
  pnpm --filter server test:int \
  --cacheDirectory="$VT_EVIDENCE/jest/int-$WORKTREE_NAME"
'
```

The repository already serializes suites inside each database with Jest `maxWorkers: 1`; concurrency occurs only between isolated worktrees.

## Stuck-job diagnosis

Capture the queue’s authoritative state—`documents.ingest_status` is not a substitute for `pgboss.job`:

```bash
for db in vietnam_v3_fa_ingestion_test vietnam_v3_fb_ingestion_test; do
  docker compose -f /Users/kien.ha/Code/vietnam/docker-compose.yml exec -T postgres \
    psql -X -P pager=off -U vft_user -d "$db" -c \
    "SELECT now(),id,name,state,retry_count,retry_limit,created_on,start_after,started_on,completed_on,output,data
     FROM pgboss.job
     WHERE name IN ('ingest.text','ingest.url')
     ORDER BY created_on;" > "$VT_EVIDENCE/sql/$db-jobs.txt"

  docker compose -f /Users/kien.ha/Code/vietnam/docker-compose.yml exec -T postgres \
    psql -X -P pager=off -U vft_user -d "$db" -c \
    "SELECT pid,state,wait_event_type,wait_event,query_start,
            pg_blocking_pids(pid) AS blocked_by,left(query,180) AS query
     FROM pg_stat_activity WHERE datname=current_database();" \
    > "$VT_EVIDENCE/sql/$db-activity.txt"
done
```

Correlate `data->>'documentId'` with worker logs, document existence, excerpts, retry count, timestamps, and `output`. A due `created/retry` job with no worker log points first to the known missing-worker condition; an old `active` job with wait events or blockers points to database contention; repeated retries with `output` point to handler failure.

## Parallel-only failures

1. Preserve `int/summary.json`, all logs, SQL snapshots, path, branch, HEAD, dirty state, and allocation.
2. Rerun only the failing worktree with the identical database, command, and cache path; write to `$VT_EVIDENCE/solo`.
3. If it passes alone, rerun the three-worktree matrix with `--max-parallel 1`, then vary one shared mechanism at a time: stop the two tracked debug workers, use fresh per-run temp/cache directories, inspect PostgreSQL blockers, then record CPU/memory pressure.
4. If it also fails alone, follow `docs/DEBUG.md`: reproduce concretely, keep `AI_PROVIDER=mock`, and diagnose it as branch/environment code rather than concurrency.
5. Report the first diverging resource or mechanism, not merely “race condition.”

Run package-scoped follow-up checks per worktree: `pnpm --filter server test` and `pnpm --filter web type-check`. The web workspace has no unit-test script; do not report one. Do not trust root `pnpm test` as the integration result.

Stop workers only by interrupting their tracked matrix terminal, which terminates those exact process groups. Never use `pkill`, stop another checkout’s process, or run `docker compose down`.

Final handoff row:

```text
path | branch@HEAD | dirty | changed files | test:int exit | unit exit | web type-check exit | log | blocker
```

Cleanup inspection only:

```bash
git -C /Users/kien.ha/Code/vietnam worktree prune --dry-run
```

Nothing was executed; no repository, Git metadata, process, database, or remote state changed.

<oai-mem-citation>
<citation_entries>
MEMORY.md:1-3|note=[Used repository source precedence and live checkout guidance]
</citation_entries>
<rollout_ids>
019f70f3-9089-7231-bb94-5118f5ddd93b
</rollout_ids>
</oai-mem-citation>
