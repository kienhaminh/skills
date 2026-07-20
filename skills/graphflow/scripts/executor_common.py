#!/usr/bin/env python3
"""Shared, dependency-free contracts for Graphflow executors."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


DIGEST_PREFIX = "sha256:"
RESULT_STATUSES = {"succeeded", "decompose", "waiting_user", "waiting_approval", "waiting_external", "blocked", "failed"}
QUESTION_IMPACTS = {
    "objective", "acceptance", "scope", "authority", "intent_baseline",
    "verification_oracle", "cost_risk", "irreversible_action",
}
SEMANTIC_QUESTION_IMPACTS = {"objective", "acceptance", "scope", "intent_baseline", "verification_oracle"}
AUTHORITY_CAPABILITIES = {"local_write", "commit", "push", "pull_request", "merge", "deploy", "destructive", "network", "credentials"}
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {label}: {error}") from error


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def fsync_directory(path: Path) -> None:
    """Best-effort durability for an atomic rename's directory entry."""
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY)
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        if descriptor is not None:
            os.close(descriptor)


def append_event(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def sha256(path: Path) -> str:
    return DIGEST_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def json_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return DIGEST_PREFIX + hashlib.sha256(encoded).hexdigest()


def canonical_graph_digest(graph: dict[str, Any]) -> str:
    semantic = json.loads(json.dumps(graph))
    semantic.pop("lifecycle", None)
    semantic.pop("verification", None)
    for node in semantic.get("nodes", []):
        if isinstance(node, dict):
            for field in ("status", "runtime", "retry"):
                node.pop(field, None)
    return json_digest(semantic)


def question_surface_digest(graph: dict[str, Any]) -> str:
    semantic = json.loads(json.dumps(graph))
    semantic.pop("lifecycle", None)
    semantic.pop("verification", None)
    gate = semantic.get("question_gate")
    if isinstance(gate, dict):
        gate.pop("review", None)
    integrity = semantic.get("integrity")
    if isinstance(integrity, dict):
        for field in ("status", "plan_digest", "runner_digest"):
            integrity.pop(field, None)
    for node in semantic.get("nodes", []):
        if isinstance(node, dict):
            for field in ("status", "runtime", "retry"):
                node.pop(field, None)
    return json_digest(semantic)


def inside(root: Path, relative: str, label: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError(f"{label} must be a non-empty relative path")
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"{label} escapes its root")
    return target


def node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node.get("id")): node for node in graph.get("nodes", []) if isinstance(node, dict)}


def load_executor(workflow_dir: Path, node_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    graph = load_json(workflow_dir / "graph.json", "graph")
    if not isinstance(graph, dict):
        raise ValueError("graph must be an object")
    node = node_map(graph).get(node_id)
    if node is None:
        raise ValueError(f"unknown node {node_id}")
    link = node.get("executor")
    if not isinstance(link, dict):
        raise ValueError(f"node {node_id} has no executor")
    if link.get("schema_version") != 1 or link.get("type") not in {"command", "agent"}:
        raise ValueError("executor link has an unsupported schema or type")
    spec_path = inside(workflow_dir, link.get("spec"), "executor.spec")
    expected_digest = link.get("digest")
    if not isinstance(expected_digest, str) or sha256(spec_path) != expected_digest:
        raise ValueError(f"executor spec digest mismatch for node {node_id}")
    spec = load_json(spec_path, "executor spec")
    if not isinstance(spec, dict):
        raise ValueError("executor spec must be an object")
    validate_spec(spec, node_id, str(link["type"]), workflow_dir)
    return graph, node, spec, inside(workflow_dir, link.get("result"), "executor.result")


def validate_spec(spec: dict[str, Any], node_id: str, executor_type: str, workflow_dir: Path) -> None:
    common = {
        "schema_version", "node_id", "type", "workspace", "timeout_seconds", "idempotency_key",
        "result_schema", "acceptance_checks", "env_allow", "resources", "requires_authority",
    }
    allowed = common | ({"argv"} if executor_type == "command" else {"prompt", "model", "reasoning_effort", "sandbox"})
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise ValueError(f"executor spec has unknown fields: {unknown}")
    if spec.get("schema_version") != 2 or spec.get("node_id") != node_id or spec.get("type") != executor_type:
        raise ValueError("executor spec identity does not match graph link")
    workspace = spec.get("workspace")
    if not isinstance(workspace, dict) or set(workspace) != {"mode", "ref", "subdir"}:
        raise ValueError("executor workspace must contain exactly mode, ref, and subdir")
    if workspace.get("mode") not in {"primary", "worktree", "integration", "verifier"}:
        raise ValueError("executor workspace mode is invalid")
    if not isinstance(workspace.get("ref"), str) or not workspace["ref"]:
        raise ValueError("executor workspace ref must be non-empty")
    subdir = workspace.get("subdir")
    if not isinstance(subdir, str) or not subdir or Path(subdir).is_absolute() or ".." in Path(subdir).parts:
        raise ValueError("executor workspace subdir must be a safe relative path")
    timeout = spec.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 86400:
        raise ValueError("executor timeout_seconds must be between 1 and 86400")
    if not isinstance(spec.get("idempotency_key"), str) or not spec["idempotency_key"].strip():
        raise ValueError("executor idempotency_key must be non-empty")
    inside(workflow_dir, spec.get("result_schema"), "executor.result_schema")
    checks = spec.get("acceptance_checks")
    if not isinstance(checks, list) or not checks or any(not isinstance(item, str) or not item for item in checks):
        raise ValueError("executor acceptance_checks must be a non-empty string list")
    env_allow = spec.get("env_allow", [])
    if not isinstance(env_allow, list) or any(not isinstance(item, str) or not item for item in env_allow):
        raise ValueError("executor env_allow must be a string list")
    authority = spec.get("requires_authority")
    if not isinstance(authority, list) or len(authority) != len(set(authority)) or any(item not in AUTHORITY_CAPABILITIES for item in authority):
        raise ValueError("executor requires_authority contains invalid or duplicate capabilities")
    resources = spec.get("resources")
    if not isinstance(resources, list) or not resources:
        raise ValueError("executor resources must lock at least the result schema")
    seen_resources: set[str] = set()
    for resource in resources:
        if not isinstance(resource, dict) or set(resource) != {"path", "digest"}:
            raise ValueError("executor resources must contain exactly path and digest")
        path_value = resource.get("path")
        if not isinstance(path_value, str) or path_value in seen_resources:
            raise ValueError("executor resource paths must be unique strings")
        path = inside(workflow_dir, path_value, "executor.resources.path")
        if not path.is_file() or resource.get("digest") != sha256(path):
            raise ValueError(f"executor resource digest mismatch: {path_value}")
        seen_resources.add(path_value)
    if spec.get("result_schema") not in seen_resources:
        raise ValueError("executor resources must lock result_schema")
    if executor_type == "agent" and spec.get("prompt") not in seen_resources:
        raise ValueError("agent resources must lock prompt")
    if executor_type == "command":
        argv = spec.get("argv")
        if not isinstance(argv, list) or not argv or any(not isinstance(item, str) or not item for item in argv):
            raise ValueError("command executor argv must be a non-empty string list")
    else:
        inside(workflow_dir, spec.get("prompt"), "executor.prompt")
        if spec.get("sandbox") not in {"read-only", "workspace-write"}:
            raise ValueError("agent sandbox must be read-only or workspace-write")
        if spec.get("model") is not None and (not isinstance(spec["model"], str) or not spec["model"]):
            raise ValueError("agent model must be null or a non-empty string")
        if spec.get("reasoning_effort") not in {None, "low", "medium", "high", "xhigh", "max", "ultra"}:
            raise ValueError("agent reasoning_effort is invalid")


def validate_result(result: Any, workflow_id: str, node_id: str, attempt: int, idempotency_key: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["result must be an object"]
    required = {
        "schema_version", "workflow_id", "node_id", "attempt", "idempotency_key", "status", "summary",
        "outputs", "evidence", "memory_delta", "request", "decomposition", "usage",
    }
    allowed = required | {"verification"}
    if not required.issubset(result) or not set(result).issubset(allowed):
        errors.append(f"result fields must contain {sorted(required)} and may additionally contain verification")
    expected = {
        "schema_version": 2,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "attempt": attempt,
        "idempotency_key": idempotency_key,
    }
    for field, value in expected.items():
        if result.get(field) != value:
            errors.append(f"{field} must equal {value!r}")
    status = result.get("status")
    if status not in RESULT_STATUSES:
        errors.append("status is invalid")
    if not isinstance(result.get("summary"), str) or not result["summary"].strip():
        errors.append("summary must be non-empty")
    for field in ("outputs", "evidence"):
        if not isinstance(result.get(field), list):
            errors.append(f"{field} must be a list")
    if result.get("memory_delta") is not None and not isinstance(result.get("memory_delta"), dict):
        errors.append("memory_delta must be null or an object")
    request = result.get("request")
    waiting = status in {"waiting_user", "waiting_approval"}
    if waiting and not isinstance(request, dict):
        errors.append("waiting result requires request")
    if not waiting and request is not None:
        errors.append("request is allowed only for user/approval waiting states")
    decomposition = result.get("decomposition")
    if status == "decompose" and not isinstance(decomposition, dict):
        errors.append("decompose result requires decomposition")
    if status != "decompose" and decomposition is not None:
        errors.append("decomposition is allowed only for decompose status")
    if status == "decompose":
        if result.get("outputs") != [] or result.get("evidence") != []:
            errors.append("decompose result must leave outputs and evidence empty")
        if result.get("memory_delta") is not None or request is not None:
            errors.append("decompose result must leave memory_delta and request null")
    verification = result.get("verification")
    if verification is not None:
        verification_fields = {"schema_version", "outcome", "challenge_classes", "claims", "limitations"}
        if status != "succeeded":
            errors.append("verification is allowed only for succeeded status")
        if not isinstance(verification, dict) or set(verification) != verification_fields:
            errors.append(f"verification must contain exactly {sorted(verification_fields)}")
        else:
            if verification.get("schema_version") != 1 or verification.get("outcome") not in {"pass", "fail"}:
                errors.append("verification schema/outcome is invalid")
            for field in ("challenge_classes", "claims", "limitations"):
                if not isinstance(verification.get(field), list):
                    errors.append(f"verification.{field} must be a list")
    if isinstance(request, dict):
        request_fields = {"request_id", "digest", "question", "alternatives", "risks", "triage"}
        if set(request) != request_fields:
            errors.append(f"request fields must equal {sorted(request_fields)}")
        for field in ("request_id", "digest", "question"):
            if not isinstance(request.get(field), str) or not request[field].strip():
                errors.append(f"request.{field} must be non-empty")
        for field in ("alternatives", "risks"):
            values = request.get(field)
            if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value.strip() for value in values):
                errors.append(f"request.{field} must be a non-empty string list")
        triage = request.get("triage")
        triage_fields = {
            "blocking_scope", "impacts", "affected_nodes", "no_safe_default_reason",
            "resolution_mode", "request_graph_digest", "authority_capabilities",
        }
        if not isinstance(triage, dict) or set(triage) != triage_fields:
            errors.append(f"request.triage must contain exactly {sorted(triage_fields)}")
        else:
            if triage.get("blocking_scope") not in {"branch", "workflow"}:
                errors.append("request.triage.blocking_scope must be branch or workflow")
            impacts = triage.get("impacts")
            if not isinstance(impacts, list) or not impacts or any(value not in QUESTION_IMPACTS for value in impacts) or len(impacts) != len(set(impacts)):
                errors.append("request.triage.impacts must be a unique non-empty controlled list")
            affected = triage.get("affected_nodes")
            if not isinstance(affected, list) or not affected or any(not isinstance(value, str) or not value for value in affected) or len(affected) != len(set(affected)):
                errors.append("request.triage.affected_nodes must be a unique non-empty string list")
            if node_id not in affected:
                errors.append("request.triage.affected_nodes must include the requesting node")
            reason = triage.get("no_safe_default_reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append("request.triage.no_safe_default_reason must be non-empty")
            resolution_mode = triage.get("resolution_mode")
            if resolution_mode not in {"resume", "rebase"}:
                errors.append("request.triage.resolution_mode must be resume or rebase")
            elif isinstance(impacts, list) and SEMANTIC_QUESTION_IMPACTS.intersection(impacts) and resolution_mode != "rebase":
                errors.append("semantic impacts require request.triage.resolution_mode rebase")
            request_graph_digest = triage.get("request_graph_digest")
            if not isinstance(request_graph_digest, str) or not DIGEST_RE.fullmatch(request_graph_digest):
                errors.append("request.triage.request_graph_digest must be sha256:<64 lowercase hex>")
            capabilities = triage.get("authority_capabilities")
            if not isinstance(capabilities, list) or len(capabilities) != len(set(capabilities)) or any(value not in AUTHORITY_CAPABILITIES for value in capabilities):
                errors.append("request.triage.authority_capabilities must be a unique controlled list")
            elif isinstance(impacts, list):
                if "authority" in impacts and not capabilities:
                    errors.append("authority impact requires request.triage.authority_capabilities")
                if "authority" not in impacts and capabilities:
                    errors.append("authority capabilities are allowed only for authority impact")
    if not isinstance(result.get("usage"), dict):
        errors.append("usage must be an object")
    return errors
