# Coding-tool adapters

Read this reference before compiling or running any `agent` executor. Command executors do not need
an agent adapter.

## Neutral process contract

Graphflow invokes the configured wrapper with no shell. The wrapper receives one compact JSON object
on stdin and must return exactly one JSON object on stdout. It may translate the request into any
coding tool's CLI, SDK, API, or in-process agent call.

Request fields are `schema_version`, `protocol`, `kind`, `prompt`, `cwd`, `output_schema`, `sandbox`,
`model_class`, resolved `model`, and `reasoning_effort`. `kind` is `node` or `review`. A node response
must match the locked node-result schema; a review response must match the Graphflow question-review
contract. Logs belong on stderr and must not contain credentials or prompt transcripts.

The wrapper owns tool-specific translation. It must:

- enforce every advertised sandbox mode; never map a requested sandbox to a weaker mode;
- keep approval interactive modes disabled and fail closed when non-interactive execution is unavailable;
- return only the final JSON value on stdout;
- preserve the requested working directory, model mapping, timeout, and structured-output contract;
- surface unsupported capability as non-zero exit instead of silently weakening the request.

## Runtime configuration

Copy or write a wrapper inside the workflow, then record it in `runtime.json`:

```json
{
  "agent_adapter": {
    "schema_version": 1,
    "protocol": "graphflow-agent-adapter-v1",
    "id": "my-tool-v1",
    "argv": ["python3", "adapters/my-tool.py"],
    "env_allow": [],
    "resources": [
      {"path": "adapters/my-tool.py", "digest": "sha256:<64 lowercase hex>"}
    ],
    "sandbox_modes": ["read-only", "workspace-write"],
    "model_map": {
      "small": "<tool-small-model>",
      "balanced": "<tool-balanced-model>",
      "frontier": "<tool-frontier-model>"
    },
    "requires_authority": ["network", "credentials"]
  }
}
```

List only environment variable names, never values. A local adapter may use an empty
`requires_authority`; a remote adapter must declare `network`, and any adapter or executor env
allowlist requires `credentials`. Every agent executor must declare the adapter's requirements so
normal node-scoped authority checks can grant them before launch. Keep the wrapper workflow-relative and
digest-locked. Graphflow rejects missing adapters, unlocked local wrapper paths, resource drift,
unsupported sandbox modes, or unmapped model classes before dispatch.

## Tool-specific wrappers

- [codex-cli.py](../assets/adapter-templates/codex-cli.py) is an optional compatibility adapter for
  Codex CLI. Copy it into `<workflow>/adapters/`; Codex remains one adapter, not a core dependency.

There is deliberately no generic prompt/stdin adapter: forwarding the requested sandbox as metadata
does not prove that a downstream tool enforces it. For every other coding tool, create a small
tool-specific wrapper that translates the neutral request into that tool's supported non-interactive,
sandbox, model, and structured-output controls. Do not claim support until both an ordinary node and
an independent review pass through the adapter with fresh runtime evidence.

Changing an adapter, its model map, or its advertised capabilities is a runtime contract change.
Recompute resource digests and rerun executable validation before resuming.
