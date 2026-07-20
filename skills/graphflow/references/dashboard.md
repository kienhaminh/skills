# Local workflow dashboard

The dashboard is a read-only projection of canonical `graph.json`; it never owns state or actions.

## Create + serve

Copy the bundled dashboard unchanged into the workflow artifact:

```bash
cp -R <skill-dir>/assets/workflow-template/dashboard .codex/workflows/<id>/dashboard
python3 <skill-dir>/scripts/serve_dashboard.py serve .codex/workflows/<id> --port 8765 --max-port 8799
```

Record PID/port in `runtime.json`. Verify HTTP 200 for `/dashboard/`, `/graph.json`, `/runtime.json`, and `/memory/state.json`. Stop with `python3 <skill-dir>/scripts/serve_dashboard.py stop <workflow-dir>`; never use a broad kill command.

## Projection contract

The bundled static dashboard:

- fetches graph, runtime, sanitized requests/progress/workspaces/primary-checkout state, and shared-memory projections; polls while visible and refreshes on `visibilitychange`;
- renders lifecycle, Goal-independent scheduler state, structural-decomposition status/revision, Ship delivery status/branch, primary-checkout guard, trust phase/workspace/branch/HEAD, executor type/spec, question/intent/integrity/evidence gates, sanitized confirmation queue, memory revision/pivotal entries, coverage, frontier, dependencies, methods, scopes, budgets, and runtime summaries;
- uses DOM `textContent`, no HTML injection, remote scripts, CDN, analytics, credentials, or write controls;
- tolerates a transient invalid/partial read and shows last refresh/error state.

Adapt the graph, not dashboard code. Change dashboard assets only for a real projection requirement, then run `node --check dashboard/app.js` and a loopback endpoint check.

## Security + exposure

Default bind is `127.0.0.1`. Do not expose publicly, add authentication state, or include secrets/process arguments. A remote dashboard is a separate product/security task requiring explicit authority and threat analysis.

Dashboard health is observational evidence only. It does not prove graph validity, product behavior, or completion.
