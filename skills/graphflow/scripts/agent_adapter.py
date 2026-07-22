#!/usr/bin/env python3
"""Provider-neutral process contract for Graphflow agent executors."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from executor_common import inside, load_json, sha256


PROTOCOL = "graphflow-agent-adapter-v1"
ADAPTER_FIELDS = {
    "schema_version", "protocol", "id", "argv", "env_allow", "resources",
    "sandbox_modes", "model_map", "requires_authority",
}
MODEL_CLASSES = {"small", "balanced", "frontier"}
SANDBOX_MODES = {"read-only", "workspace-write"}
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def allowed_environment(names: list[str]) -> dict[str, str]:
    baseline = {name: os.environ[name] for name in ("PATH", "LANG", "LC_ALL", "TMPDIR") if name in os.environ}
    for name in names:
        if name in os.environ:
            baseline[name] = os.environ[name]
    return baseline


def load_adapter(workflow_dir: Path) -> dict[str, Any]:
    runtime = load_json(workflow_dir / "runtime.json", "runtime agent adapter")
    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object")
    adapter = runtime.get("agent_adapter")
    if adapter is None:
        raise ValueError("runtime.agent_adapter must be configured before dispatching agent nodes")
    if not isinstance(adapter, dict) or set(adapter) != ADAPTER_FIELDS:
        raise ValueError(f"runtime.agent_adapter must contain exactly {sorted(ADAPTER_FIELDS)!r}")
    if adapter.get("schema_version") != 1 or adapter.get("protocol") != PROTOCOL:
        raise ValueError(f"runtime.agent_adapter must use {PROTOCOL}")
    if not isinstance(adapter.get("id"), str) or not adapter["id"].strip():
        raise ValueError("runtime.agent_adapter.id must be non-empty")

    argv = adapter.get("argv")
    if not isinstance(argv, list) or not argv or any(not isinstance(item, str) or not item for item in argv):
        raise ValueError("runtime.agent_adapter.argv must be a non-empty string list")
    if any(Path(item).is_absolute() for item in argv[1:]):
        raise ValueError("runtime.agent_adapter argv arguments must be portable; absolute paths are not allowed")

    env_allow = adapter.get("env_allow")
    if (
        not isinstance(env_allow, list)
        or len(env_allow) != len(set(env_allow))
        or any(not isinstance(item, str) or not ENV_NAME_RE.fullmatch(item) for item in env_allow)
    ):
        raise ValueError("runtime.agent_adapter.env_allow must contain unique environment variable names")

    sandbox_modes = adapter.get("sandbox_modes")
    if (
        not isinstance(sandbox_modes, list)
        or not sandbox_modes
        or len(sandbox_modes) != len(set(sandbox_modes))
        or any(item not in SANDBOX_MODES for item in sandbox_modes)
    ):
        raise ValueError("runtime.agent_adapter.sandbox_modes must contain supported Graphflow sandbox modes")

    model_map = adapter.get("model_map")
    if not isinstance(model_map, dict) or any(
        key not in MODEL_CLASSES or not isinstance(value, str) or not value
        for key, value in model_map.items()
    ):
        raise ValueError("runtime.agent_adapter.model_map must map Graphflow model classes to non-empty tool model selectors")
    authority = adapter.get("requires_authority")
    if (
        not isinstance(authority, list)
        or len(authority) != len(set(authority))
        or any(item not in {"network", "credentials"} for item in authority)
    ):
        raise ValueError("runtime.agent_adapter.requires_authority may contain only network and credentials")
    if env_allow and "credentials" not in authority:
        raise ValueError("runtime.agent_adapter env_allow requires credentials authority")

    resources = adapter.get("resources")
    if not isinstance(resources, list) or not resources:
        raise ValueError("runtime.agent_adapter.resources must lock at least one adapter wrapper")
    resource_paths: set[str] = set()
    for resource in resources:
        if not isinstance(resource, dict) or set(resource) != {"path", "digest"}:
            raise ValueError("runtime.agent_adapter.resources entries must contain exactly path and digest")
        value = resource.get("path")
        if not isinstance(value, str) or value in resource_paths:
            raise ValueError("runtime.agent_adapter resource paths must be unique strings")
        path = inside(workflow_dir, value, "runtime.agent_adapter.resources.path")
        if not path.is_file() or resource.get("digest") != sha256(path):
            raise ValueError(f"runtime.agent_adapter resource digest mismatch: {value}")
        resource_paths.add(value)

    local_argv = {
        item for item in argv
        if not item.startswith("-") and not Path(item).is_absolute() and ("/" in item or item.startswith("."))
    }
    unlocked = sorted(local_argv - resource_paths)
    if unlocked:
        raise ValueError(f"runtime.agent_adapter argv references unlocked local resources: {unlocked}")
    if not local_argv:
        raise ValueError("runtime.agent_adapter.argv must invoke at least one digest-locked workflow-local wrapper")
    return adapter


def validate_executor(workflow_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    adapter = load_adapter(workflow_dir)
    sandbox = spec.get("sandbox")
    if sandbox not in adapter["sandbox_modes"]:
        raise ValueError(f"agent adapter {adapter['id']!r} does not support sandbox mode {sandbox!r}")
    model_class = spec.get("model_class")
    if model_class is not None and model_class not in adapter["model_map"]:
        raise ValueError(f"agent adapter {adapter['id']!r} has no model mapping for {model_class!r}")
    declared = set(spec.get("requires_authority", []))
    missing = sorted(set(adapter["requires_authority"]) - declared)
    if missing:
        raise ValueError(f"agent executor must declare adapter authority: {', '.join(missing)}")
    if spec.get("env_allow") and "credentials" not in declared:
        raise ValueError("agent executor env_allow requires credentials authority")
    return adapter


def resolved_argv(workflow_dir: Path, adapter: dict[str, Any]) -> list[str]:
    resources = {item["path"] for item in adapter["resources"]}
    return [str(inside(workflow_dir, item, "runtime.agent_adapter.argv")) if item in resources else item for item in adapter["argv"]]


def invoke(
    workflow_dir: Path,
    request: dict[str, Any],
    *,
    timeout_seconds: int,
    executor_env_allow: list[str] | None = None,
    declared_authority: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Invoke one adapter and return its JSON result plus sanitized execution metadata."""
    adapter = load_adapter(workflow_dir)
    missing_authority = sorted(set(adapter["requires_authority"]) - set(declared_authority or []))
    if missing_authority:
        raise ValueError(f"agent adapter authority is missing: {', '.join(missing_authority)}")
    sandbox = request.get("sandbox")
    if sandbox not in adapter["sandbox_modes"]:
        raise ValueError(f"agent adapter {adapter['id']!r} does not support sandbox mode {sandbox!r}")
    model_class = request.get("model_class")
    if model_class is not None:
        if model_class not in MODEL_CLASSES:
            raise ValueError(f"unsupported Graphflow model class: {model_class!r}")
        if model_class not in adapter["model_map"]:
            raise ValueError(f"agent adapter {adapter['id']!r} has no model mapping for {model_class!r}")
        request = dict(request)
        request["model"] = adapter["model_map"][model_class]
    else:
        request = dict(request)
        request["model"] = None

    environment_names = list(adapter["env_allow"])
    for name in executor_env_allow or []:
        if name not in environment_names:
            environment_names.append(name)
    if environment_names and "credentials" not in set(declared_authority or []):
        raise ValueError("agent adapter environment requires credentials authority")
    try:
        completed = subprocess.run(
            resolved_argv(workflow_dir, adapter),
            input=json.dumps(request, sort_keys=True, separators=(",", ":")),
            cwd=Path(str(request["cwd"])),
            env=allowed_environment(environment_names),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"agent adapter {adapter['id']!r} failed to run: {error}") from error
    metadata = {
        "schema_version": 1,
        "adapter_id": adapter["id"],
        "protocol": PROTOCOL,
        "kind": request.get("kind"),
        "exit_code": completed.returncode,
    }
    if completed.returncode != 0:
        raise ValueError(f"agent adapter {adapter['id']!r} exited with {completed.returncode}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(f"agent adapter {adapter['id']!r} did not return one JSON value") from error
    if not isinstance(result, dict):
        raise ValueError(f"agent adapter {adapter['id']!r} result must be an object")
    return result, metadata
