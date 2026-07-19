# Parallel worktree execution plan

## Goal

Create two isolated feature worktrees from the exact current `dev` commit, assign one agent to search ranking and one to map rendering, run supported verification concurrently with isolated test databases, then keep four development processes running simultaneously on non-conflicting ports.

## Current baseline

- Main checkout: `/Users/kien.ha/Code/vietnam`
- Branch: `dev`
- Commit: `9b75e054422c3e20ddf27c1a5bf73e5fda82b9c6`
- Status: clean and equal to the locally known `origin/dev`
- Registered worktrees: main checkout only
- Proposed branches do not currently exist locally or in local remote-tracking refs.
- Node `v22.16.0` and pnpm `10.29.2` satisfy repository requirements.
- `vft-postgres` is healthy on port `5434`.
- Ports `3201`, `3202`, `8201`, and `8202` were free when inspected.
- The repository lockfile exists but is ignored and untracked. Each new worktree therefore needs an exact copied lockfile plus an offline frozen install.
- Unit and integration tests exist only for `apps/server`; the web app has no test suite. Use web type-check, targeted lint, build, and browser behavior as its validation.
- Do not use root `pnpm test`; [docs/TESTING.md](/Users/kien.ha/Code/vietnam/docs/TESTING.md:37) requires the `server`-filtered command.
- Map data is already known to be incomplete; do not report that as a rendering regression unless the feature changes the data source itself ([tech-debt.md](/Users/kien.ha/Code/vietnam/docs/plans/tech-debt.md:36)).

## Resource allocation

| Owner | Branch and worktree | Scope | Dev ports | Test database | Heavy-job limit | Evidence |
|---|---|---|---|---|---|---|
| Coordinator | Main `dev` checkout | Preflight, worktree creation, dependency/bootstrap gates, final integration review | None | None | No build/test job | Baseline SHA, worktree list, branch/path checks |
| Search agent | `codex/search-ranking` at `.codex/worktrees/search-ranking` | Search service, contracts/API route/search UI only | API `8201`, web `3201` | `vietnam_search_test` | One test/build command at a time | Search tests, ranking JSON, health probes, diff |
| Map agent | `codex/map-rendering` at `.codex/worktrees/map-rendering` | Map page, hooks, Three.js scene/controllers/assets only | API `8202`, web `3202` | `vietnam_map_test` | One test/build command at a time | Static checks, screenshots, interaction notes, diff |

Dispatch both agents together. Each agent runs its sequence serially, so at most two heavy commands execute concurrently. Start the four development processes only after both verification sequences finish.

## 1. Preflight and create the worktrees

Run from a coordinator terminal:

```zsh
set -euo pipefail

VFT_REPO=/Users/kien.ha/Code/vietnam
VFT_SEARCH_WT="$VFT_REPO/.codex/worktrees/search-ranking"
VFT_MAP_WT="$VFT_REPO/.codex/worktrees/map-rendering"
VFT_SEARCH_BRANCH=codex/search-ranking
VFT_MAP_BRANCH=codex/map-rendering

test "$(git -C "$VFT_REPO" branch --show-current)" = dev
test -z "$(git -C "$VFT_REPO" status --porcelain)"
git -C "$VFT_REPO" check-ignore -q .codex/

VFT_BASE_SHA="$(git -C "$VFT_REPO" rev-parse --verify 'dev^{commit}')"
VFT_REMOTE_DEV_SHA="$(
  git -C "$VFT_REPO" ls-remote origin refs/heads/dev |
  awk 'NR == 1 { print $1 }'
)"
test -n "$VFT_REMOTE_DEV_SHA"
test "$VFT_BASE_SHA" = "$VFT_REMOTE_DEV_SHA"

for VFT_REF in "$VFT_SEARCH_BRANCH" "$VFT_MAP_BRANCH"; do
  if git -C "$VFT_REPO" show-ref --verify --quiet "refs/heads/$VFT_REF"; then
    echo "Stop: local branch already exists: $VFT_REF" >&2
    exit 1
  fi
done

VFT_REMOTE_FEATURE_REFS="$(
  git -C "$VFT_REPO" ls-remote --heads origin \
    "refs/heads/$VFT_SEARCH_BRANCH" \
    "refs/heads/$VFT_MAP_BRANCH"
)"
test -z "$VFT_REMOTE_FEATURE_REFS"

test ! -e "$VFT_SEARCH_WT"
test ! -e "$VFT_MAP_WT"
test -f "$VFT_REPO/pnpm-lock.yaml"

for VFT_PORT in 3201 3202 8201 8202; do
  if lsof -nP -iTCP:"$VFT_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Stop: port $VFT_PORT is already occupied" >&2
    exit 1
  fi
done

mkdir -p "$VFT_REPO/.codex/worktrees"
git -C "$VFT_REPO" worktree add \
  -b "$VFT_SEARCH_BRANCH" "$VFT_SEARCH_WT" "$VFT_BASE_SHA"
git -C "$VFT_REPO" worktree add \
  -b "$VFT_MAP_BRANCH" "$VFT_MAP_WT" "$VFT_BASE_SHA"

test "$(git -C "$VFT_SEARCH_WT" rev-parse HEAD)" = "$VFT_BASE_SHA"
test "$(git -C "$VFT_MAP_WT" rev-parse HEAD)" = "$VFT_BASE_SHA"
test "$(git -C "$VFT_SEARCH_WT" branch --show-current)" = "$VFT_SEARCH_BRANCH"
test "$(git -C "$VFT_MAP_WT" branch --show-current)" = "$VFT_MAP_BRANCH"

git -C "$VFT_REPO" worktree list --porcelain
```

If either `worktree add` fails, stop and report the exact state. Do not automatically remove the successfully created worktree.

## 2. Reproduce dependencies without changing dependency resolution

```zsh
set -euo pipefail

VFT_REPO=/Users/kien.ha/Code/vietnam
VFT_SEARCH_WT="$VFT_REPO/.codex/worktrees/search-ranking"
VFT_MAP_WT="$VFT_REPO/.codex/worktrees/map-rendering"
VFT_LOCK_SHA="$(shasum -a 256 "$VFT_REPO/pnpm-lock.yaml" | awk '{print $1}')"

for VFT_WT in "$VFT_SEARCH_WT" "$VFT_MAP_WT"; do
  cp "$VFT_REPO/pnpm-lock.yaml" "$VFT_WT/pnpm-lock.yaml"
  test "$(shasum -a 256 "$VFT_WT/pnpm-lock.yaml" | awk '{print $1}')" = "$VFT_LOCK_SHA"

  (
    cd "$VFT_WT"
    pnpm install --offline --frozen-lockfile
    test -z "$(git status --porcelain)"
  )
done
```

If the offline install reports a missing package, stop. Do not remove `--offline`, update the lockfile, or perform a network install without separate approval.

## 3. Provision isolated integration databases

Never point integration tests at `vietnam_v3`: the harness truncates tables. Both names below satisfy its required `_test` suffix.

```zsh
set -euo pipefail

for VFT_TEST_DB in vietnam_search_test vietnam_map_test; do
  if ! docker exec vft-postgres \
    psql -U vft_user -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$VFT_TEST_DB'" |
    tr -d '[:space:]' |
    grep -qx 1; then
    docker exec vft-postgres createdb -U vft_user "$VFT_TEST_DB"
  fi

  docker exec vft-postgres \
    psql -v ON_ERROR_STOP=1 -U vft_user -d "$VFT_TEST_DB" \
    -c 'CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;'
done

(
  cd /Users/kien.ha/Code/vietnam/.codex/worktrees/search-ranking
  DATABASE_URL=postgresql://vft_user:vft_password@localhost:5434/vietnam_search_test \
    pnpm --filter @vietnam/db db:migrate
) &

(
  cd /Users/kien.ha/Code/vietnam/.codex/worktrees/map-rendering
  DATABASE_URL=postgresql://vft_user:vft_password@localhost:5434/vietnam_map_test \
    pnpm --filter @vietnam/db db:migrate
) &

wait
```

Do not run `docker compose down -v` or drop either test database during cleanup.

## 4. Dispatch the agents concurrently

Give each agent only its standalone prompt.

### Search-ranking agent prompt

> Work only in `/Users/kien.ha/Code/vietnam/.codex/worktrees/search-ranking` on branch `codex/search-ranking`. Improve or debug search ranking without touching map-rendering files. Read `docs/README.md`, `docs/CONVENTIONS.md`, `docs/TESTING.md`, `docs/DEBUG.md`, and `docs/plans/tech-debt.md` before editing. Reproduce the ranking problem before changing code. The current implementation is centered on `apps/server/src/knowledge/knowledge-search.service.ts`, its unit spec, `apps/server/src/int/knowledge-search.int-spec.ts`, shared knowledge contracts, and the web search proxy/UI. Use `AI_PROVIDER=mock`; do not make LLM network calls. Keep SQL behavior covered by an integration test. Do not use the dev database for tests. Do not commit, push, remove worktrees, or touch the other worktree. Run the exact search verification sequence below, preserve logs under `.codex/evidence`, then start the search API on 8201 and web app on 3201 using the runtime commands below. Hand back the starting SHA, changed files, reproduction, cause, tests with pass counts, health/search probe output, remaining uncertainty, and `git diff --check`.

### Map-rendering agent prompt

> Work only in `/Users/kien.ha/Code/vietnam/.codex/worktrees/map-rendering` on branch `codex/map-rendering`. Improve or debug map rendering without touching search-ranking files. Read `docs/README.md`, `docs/CONVENTIONS.md`, `docs/TESTING.md`, `docs/DEBUG.md`, and `docs/plans/tech-debt.md` before editing. Reproduce the rendering problem before changing code. The current surface is `apps/web/app/[locale]/map`, `apps/web/components/map`, `apps/web/lib/map`, and `apps/web/public/map`. The known missing/outdated ward data is out of scope unless explicitly asked. The web workspace has no test suite, so use targeted lint, type-check, build, browser interaction, console errors, and screenshots; do not invent a green test claim. Do not commit, push, remove worktrees, or touch the other worktree. Run the exact map verification sequence below, preserve logs under `.codex/evidence`, then start the map API on 8202 and web app on 3202 using the runtime commands below. Hand back the starting SHA, changed files, reproduction, cause, verification output, screenshots and interaction observations, remaining uncertainty, and `git diff --check`.

## 5. Run supported verification concurrently

The agents begin these sequences at the same time.

Search agent:

```zsh
set -euo pipefail
cd /Users/kien.ha/Code/vietnam/.codex/worktrees/search-ranking
mkdir -p .codex/evidence

pnpm --filter server test knowledge-search 2>&1 |
  tee .codex/evidence/focused-search-unit.log

pnpm --filter server test 2>&1 |
  tee .codex/evidence/server-unit.log

TEST_DATABASE_URL=postgresql://vft_user:vft_password@localhost:5434/vietnam_search_test \
  pnpm --filter server test:int 2>&1 |
  tee .codex/evidence/server-integration.log

pnpm --filter server lint 2>&1 |
  tee .codex/evidence/server-lint.log
pnpm type-check 2>&1 |
  tee .codex/evidence/type-check.log
pnpm build 2>&1 |
  tee .codex/evidence/build.log

git diff --check
```

Map agent:

```zsh
set -euo pipefail
cd /Users/kien.ha/Code/vietnam/.codex/worktrees/map-rendering
mkdir -p .codex/evidence

pnpm --filter server test 2>&1 |
  tee .codex/evidence/server-unit.log

TEST_DATABASE_URL=postgresql://vft_user:vft_password@localhost:5434/vietnam_map_test \
  pnpm --filter server test:int 2>&1 |
  tee .codex/evidence/server-integration.log

pnpm --filter web lint 2>&1 |
  tee .codex/evidence/web-lint.log
pnpm type-check 2>&1 |
  tee .codex/evidence/type-check.log
pnpm build 2>&1 |
  tee .codex/evidence/build.log

git diff --check
```

Use targeted workspace lint because the docs’ “root lint does nothing” statement conflicts with the current package manifests; the code/manifests take precedence.

## 6. Run both API/web pairs simultaneously

The main server env currently exists and may be sourced without copying secrets. Before starting the search web process, export a valid existing `kb:read` API key without printing it:

```zsh
export VFT_WEB_API_KEY='<existing-kb-read-key>'
```

Do not place the key in logs or command tracing.

Open four long-lived terminals.

Search API:

```zsh
set -euo pipefail
set -a
. /Users/kien.ha/Code/vietnam/apps/server/.env
set +a

export PORT=8201
export CORS_ORIGINS=http://localhost:3201
export AI_PROVIDER=mock
export INGESTION_ALLOW_PRIVATE_URLS=false

cd /Users/kien.ha/Code/vietnam/.codex/worktrees/search-ranking
pnpm --filter server dev 2>&1 | tee .codex/evidence/search-api.log
```

Search web:

```zsh
set -euo pipefail
: "${VFT_WEB_API_KEY:?Export a valid kb:read API key first}"

cd /Users/kien.ha/Code/vietnam/.codex/worktrees/search-ranking
API_URL=http://localhost:8201 \
WEB_API_KEY="$VFT_WEB_API_KEY" \
WEB_REVALIDATE_SECRET=local-debug-only \
pnpm --filter web exec next dev -p 3201 2>&1 |
  tee .codex/evidence/search-web.log
```

Map API:

```zsh
set -euo pipefail
set -a
. /Users/kien.ha/Code/vietnam/apps/server/.env
set +a

export PORT=8202
export CORS_ORIGINS=http://localhost:3202
export AI_PROVIDER=mock
export INGESTION_ALLOW_PRIVATE_URLS=false

cd /Users/kien.ha/Code/vietnam/.codex/worktrees/map-rendering
pnpm --filter server dev 2>&1 | tee .codex/evidence/map-api.log
```

Map web:

```zsh
set -euo pipefail
: "${VFT_WEB_API_KEY:?Export a valid kb:read API key first}"

cd /Users/kien.ha/Code/vietnam/.codex/worktrees/map-rendering
API_URL=http://localhost:8202 \
WEB_API_KEY="$VFT_WEB_API_KEY" \
WEB_REVALIDATE_SECRET=local-debug-only \
pnpm --filter web exec next dev -p 3202 2>&1 |
  tee .codex/evidence/map-web.log
```

Do not start either ingestion worker. The features are read paths, and two workers sharing the development queue would introduce an unrelated variable.

## 7. Live probes

```zsh
set -euo pipefail
: "${VFT_WEB_API_KEY:?}"

curl -fsS http://localhost:8201/health |
  tee /Users/kien.ha/Code/vietnam/.codex/worktrees/search-ranking/.codex/evidence/api-health.json
curl -fsS http://localhost:8202/health |
  tee /Users/kien.ha/Code/vietnam/.codex/worktrees/map-rendering/.codex/evidence/api-health.json

curl -fsS \
  -H "Authorization: Bearer $VFT_WEB_API_KEY" \
  --get \
  --data-urlencode 'q=Thánh Gióng' \
  http://localhost:8201/v1/knowledge/search |
  tee /Users/kien.ha/Code/vietnam/.codex/worktrees/search-ranking/.codex/evidence/direct-search.json

curl -fsS \
  --get \
  --data-urlencode 'q=Thánh Gióng' \
  http://localhost:3201/api/search |
  tee /Users/kien.ha/Code/vietnam/.codex/worktrees/search-ranking/.codex/evidence/web-search.json

curl -fsS -o /dev/null http://localhost:3201/vi/search
curl -fsS -o /dev/null http://localhost:3202/vi/map
curl -fsS -o /dev/null http://localhost:3202/map/provinces-geo.json
```

Use a WebGL-capable browser for `http://localhost:3202/vi/map`. Record:

1. Initial province render and absence of console errors.
2. Hover tooltip.
3. Province selection and camera transition.
4. Ward rendering after selection.
5. Clear-selection behavior.
6. Resize behavior.
7. One desktop and one narrow-viewport screenshot.

For ranking, record an ordered result table for at least one short exact query, one typo/partial query, and one four-or-more-word semantic query. Include result IDs and scores so ordering changes are reviewable.

## Safety gates

- Stop if `dev` is dirty, not checked out, or no longer matches the remote `dev` SHA.
- Stop on any branch/path/port collision; never reuse an unknown branch or directory.
- Never run integration tests against `vietnam_v3`.
- Never share one test database between concurrent Jest processes.
- Never run `docker compose down -v`, `git reset`, `git clean`, or automatic worktree removal.
- Never silently switch from offline frozen dependency installation to network installation.
- Keep `AI_PROVIDER=mock` and `INGESTION_ALLOW_PRIVATE_URLS=false`.
- Do not treat missing wards as a new rendering defect.
- Do not commit temporary logs, screenshots, `.only`, loose timeouts, or debug instrumentation.
- Do not commit or push until the user separately approves the reviewed slices.

## Handoff evidence

Each agent must return:

- Branch, worktree, starting SHA, and final SHA.
- `git status --short --branch`.
- `git diff --stat`, `git diff --check`, and a changed-file list.
- Reproduction: exact command or browser sequence, expected result, actual result.
- Root cause with fact/inference/unknown separated.
- Focused and full verification commands with exit codes and pass counts.
- Integration test database name.
- API/web URLs and health output.
- Feature-specific evidence:
  - Search: query set plus before/after ordered IDs and scores.
  - Map: console state, interaction checklist, screenshots, viewport sizes.
- Any skipped check labeled explicitly as skipped, never implied green.
- Remaining uncertainty and known debt encountered.
- Confirmation that no commit, push, cleanup, or cross-worktree edit occurred.

The coordinator then verifies both worktrees remain isolated:

```zsh
set -euo pipefail

for VFT_WT in \
  /Users/kien.ha/Code/vietnam/.codex/worktrees/search-ranking \
  /Users/kien.ha/Code/vietnam/.codex/worktrees/map-rendering
do
  git -C "$VFT_WT" status --short --branch
  git -C "$VFT_WT" diff --check
  git -C "$VFT_WT" diff --stat
done

git -C /Users/kien.ha/Code/vietnam status --short --branch
git -C /Users/kien.ha/Code/vietnam worktree list --porcelain
```

<oai-mem-citation>
<citation_entries>
MEMORY.md:1-3|note=[used repository docs and live checkout precedence]
MEMORY.md:25-30|note=[used diagnosis only debugging and evidence first routing]
</citation_entries>
<rollout_ids>
019f70f3-9089-7231-bb94-5118f5ddd93b
019f7133-4980-7613-aad9-8aa2f50052e5
</rollout_ids>
</oai-mem-citation>
