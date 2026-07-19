# Parallel worktree plan

## Goal

Create two isolated worktrees from the currently inspected `dev` commit, give each to one agent, test both concurrently, and run four simultaneous debug processes: one API and one web app per worktree.

## Current state and hard gates

Observed:

- `dev` and `origin/dev` both point to `9b75e054422c3e20ddf27c1a5bf73e5fda82b9c6`.
- The main checkout has unrelated modifications in:
  - `docs/README.md`
  - `docs/architecture/README.md`
  - `docs/design/README.md`
- Both proposed branches and sibling paths are free.
- Ports `3110`, `3210`, `8110`, and `8210` were free when inspected.
- Docker runtime access could not be verified from the current sandbox.
- `pnpm-lock.yaml` is ignored but locally present, SHA-256 `12e49f989c9c5010fe04032dd1e0009ac7082102a819cee69a1795d6c0e0896f`.

Immediately before creation, run:

```bash
cd /Users/kien.ha/Code/vietnam
git status --short --branch
git worktree list --porcelain
git branch -vv
python3 .codex/skills/worktree/scripts/worktree_matrix.py inventory --repo /Users/kien.ha/Code/vietnam
git rev-list --left-right --count dev...origin/dev
test "$(git rev-parse dev)" = 9b75e054422c3e20ddf27c1a5bf73e5fda82b9c6
test -z "$(git branch --list codex/search-ranking)"
test -z "$(git branch --list codex/map-rendering)"
test ! -e /Users/kien.ha/Code/vietnam-search-ranking
test ! -e /Users/kien.ha/Code/vietnam-map-rendering
shasum -a 256 pnpm-lock.yaml
```

Stop if the dirty-file set has changed, either branch/path is occupied, or `dev` moved. Never stage or copy the three dirty documentation files.

## Creation and dependency setup

```bash
git worktree add -b codex/search-ranking \
  /Users/kien.ha/Code/vietnam-search-ranking \
  9b75e054422c3e20ddf27c1a5bf73e5fda82b9c6

git worktree add -b codex/map-rendering \
  /Users/kien.ha/Code/vietnam-map-rendering \
  9b75e054422c3e20ddf27c1a5bf73e5fda82b9c6

cp -p /Users/kien.ha/Code/vietnam/pnpm-lock.yaml \
  /Users/kien.ha/Code/vietnam-search-ranking/pnpm-lock.yaml
cp -p /Users/kien.ha/Code/vietnam/pnpm-lock.yaml \
  /Users/kien.ha/Code/vietnam-map-rendering/pnpm-lock.yaml

shasum -a 256 /Users/kien.ha/Code/vietnam-{search-ranking,map-rendering}/pnpm-lock.yaml
```

Create an evidence directory and install independently, sharing only pnpm’s content-addressed download store:

```bash
VIETNAM_EVIDENCE_DIR="$(mktemp -d /private/tmp/vietnam-worktrees.XXXXXX)"

python3 /Users/kien.ha/Code/vietnam/.codex/skills/worktree/scripts/worktree_matrix.py run \
  --repo /Users/kien.ha/Code/vietnam \
  --worktree /Users/kien.ha/Code/vietnam-search-ranking \
  --worktree /Users/kien.ha/Code/vietnam-map-rendering \
  --max-parallel 2 \
  --log-dir "$VIETNAM_EVIDENCE_DIR/install" \
  -- pnpm install --frozen-lockfile
```

Do not copy `.env` files. Use explicit per-process environment variables.

## Resource allocation

| Slot | Owner | Worktree / branch | API | Web | Development DB | Integration DB |
|---|---|---|---:|---:|---|---|
| 0 | Search agent | `/Users/kien.ha/Code/vietnam-search-ranking` / `codex/search-ranking` | 8110 | 3110 | `vietnam_v3_search_dev` | `vietnam_v3_search_test` |
| 1 | Map agent | `/Users/kien.ha/Code/vietnam-map-rendering` / `codex/map-rendering` | 8210 | 3210 | `vietnam_v3_map_dev` | `vietnam_v3_map_test` |

Use one coordinator-owned Postgres container on host port `5434`; never run Compose from both worktrees. `docker-compose.yml` has a fixed container name, host port, and volume, so parallel Compose projects are unsafe. Before creating databases:

```bash
docker compose ps
docker ps -a --filter name=^/vft-postgres$
lsof -nP -iTCP:3110 -iTCP:3210 -iTCP:8110 -iTCP:8210 -sTCP:LISTEN
docker compose up -d postgres
docker compose exec -T postgres psql -U vft_user -d postgres -Atqc \
  "SELECT datname FROM pg_database WHERE datname IN ('vietnam_v3_search_dev','vietnam_v3_search_test','vietnam_v3_map_dev','vietnam_v3_map_test');"
```

The query must return no rows. Otherwise treat that database as occupied; do not drop or reuse it. Create all four, then run `db:init` and `db:migrate` from the owning worktree with its matching `DATABASE_URL`. Both integration names retain the mandatory `_test` suffix.

## Agent assignments

Send each agent one complete brief without the main conversation:

- Search agent owns `apps/server/src/knowledge/**`, `apps/server/src/int/knowledge-search.int-spec.ts`, `packages/contracts/src/knowledge-contracts.ts`, and the web search route/page/client. It must not touch map files.
- Map agent owns `apps/web/components/map/**`, `apps/web/lib/map/**`, and `apps/web/app/[locale]/map/**`. It must not replace `public/map` data—the repository records that dataset as incomplete and licence-uncertain—or touch search code.
- Both must avoid root configuration, Docker files, migrations, shared messages, and the dirty documentation files unless the coordinator explicitly reassigns ownership.
- Agents may edit only their worktree. Commit, merge, rebase, push, and branch deletion remain coordinator-only.
- Each agent must recheck absolute path, branch, HEAD, and status before edits, tests, and handoff.

## Concurrent verification

Do not run root `pnpm test`; it includes dead v2 tests. Run these matrix commands separately with `--max-parallel 2` and distinct log directories:

```bash
pnpm --filter server test
pnpm --filter server type-check
pnpm --filter web type-check
```

Run integration tests through the matrix runner using:

```bash
/bin/sh -ceu '
case "$WORKTREE_SLOT" in
  0) export TEST_DATABASE_URL=postgresql://vft_user:vft_password@localhost:5434/vietnam_v3_search_test ;;
  1) export TEST_DATABASE_URL=postgresql://vft_user:vft_password@localhost:5434/vietnam_v3_map_test ;;
  *) exit 64 ;;
esac
pnpm --filter server test:int
'
```

There is no web unit-test script; report that surface as unavailable. If a test fails only in parallel, preserve its log, rerun that worktree alone, then vary ports, database, cache, temp output, and resource pressure one at a time.

## Simultaneous debugging

Each agent starts two tracked terminal sessions and records their session IDs.

Search API/web:

```bash
NODE_ENV=development PORT=8110 \
DATABASE_URL=postgresql://vft_user:vft_password@localhost:5434/vietnam_v3_search_dev \
AI_PROVIDER=mock JWT_SECRET=local-only-search-ranking-debug-secret-0001 \
CORS_ORIGINS=http://localhost:3110 INGESTION_ALLOW_PRIVATE_URLS=false \
pnpm --filter server dev

API_URL=http://localhost:8110 WEB_API_KEY='<search-db-local-kb-read-key>' \
pnpm --filter web exec next dev -p 3110
```

Map API/web:

```bash
NODE_ENV=development PORT=8210 \
DATABASE_URL=postgresql://vft_user:vft_password@localhost:5434/vietnam_v3_map_dev \
AI_PROVIDER=mock JWT_SECRET=local-only-map-rendering-debug-secret-0002 \
CORS_ORIGINS=http://localhost:3210 INGESTION_ALLOW_PRIVATE_URLS=false \
pnpm --filter server dev

API_URL=http://localhost:8210 WEB_API_KEY='<map-db-local-kb-read-key>' \
pnpm --filter web exec next dev -p 3210
```

Create each key in its own development database using the supported `create-api-key -- --name ... --scopes kb:read` script after building the server. Keep plaintext keys out of logs and handoffs. Do not start workers unless the reproduction specifically requires ingestion; then use the same agent-owned database and a separately tracked session.

Verify `GET /health`, the search route on `3110`, and the map route on `3210`. Use browser screenshots plus console/network evidence for map rendering. Stop only the exact tracked sessions owned by that worktree.

## Handoff and cleanup evidence

Each agent returns exactly:

```text
path | branch@HEAD | dirty | changed files | command:exit | log | blocker
```

Attach matrix `summary.json` paths, `git diff --check`, focused test results, health response, browser evidence, process/session IDs, and confirmation that owned processes stopped. Never include API keys. The coordinator then runs:

```bash
git worktree list --porcelain
python3 /Users/kien.ha/Code/vietnam/.codex/skills/worktree/scripts/worktree_matrix.py inventory \
  --repo /Users/kien.ha/Code/vietnam
git worktree prune --dry-run
```

No worktree removal, pruning, database deletion, or branch deletion occurs without a separate clean-state and branch-fate decision.

Nothing was executed; no repository, Git metadata, process, database, or remote state changed.

<oai-mem-citation>
<citation_entries>
MEMORY.md:1-3|note=[used repository-local source routing]
MEMORY.md:28-33|note=[kept debugging grounded in docs DEBUG]
</citation_entries>
<rollout_ids>
019f70f3-9089-7231-bb94-5118f5ddd93b
</rollout_ids>
</oai-mem-citation>
