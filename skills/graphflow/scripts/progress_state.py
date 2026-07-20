#!/usr/bin/env python3
"""Maintain coordinator-owned, sanitized per-node Graphflow progress."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from executor_common import append_event, atomic_json, now_utc


PHASES = {
    "queued", "workspace_ready", "running", "heartbeat", "executor_exited",
    "scope_checking", "scope_accepted", "evidence_running", "evidence_passed",
    "verifier_running", "independently_verified", "externally_verified",
    "accepted", "decomposed", "rejected", "waiting",
}
ALLOWED_FIELDS = {
    "node_id", "phase", "at", "heartbeat_at", "workspace_ref", "branch",
    "head_sha", "changed_files", "check_id", "exit_code", "outcome", "blocker",
}
PUBLIC_FIELDS = ALLOWED_FIELDS - {"blocker"}


def update(workflow_dir: Path, node_id: str, phase: str, **values: Any) -> dict[str, Any]:
    if phase not in PHASES:
        raise ValueError(f"unsupported progress phase {phase!r}")
    value = {"node_id": node_id, "phase": phase, "at": now_utc(), **values}
    unknown = set(value) - ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"progress contains unsafe fields: {sorted(unknown)!r}")
    if not isinstance(value.get("node_id"), str) or not value["node_id"]:
        raise ValueError("progress node_id must be non-empty")
    if value.get("changed_files") is not None:
        changed = value["changed_files"]
        if not isinstance(changed, list) or any(not isinstance(item, str) for item in changed):
            raise ValueError("progress changed_files must be a string list")
    directory = workflow_dir / "runtime" / "progress"
    snapshot = directory / f"{node_id}.json"
    atomic_json(snapshot, value)
    append_event(directory / "events.jsonl", value)
    return value


def projection(workflow_dir: Path) -> list[dict[str, Any]]:
    directory = workflow_dir / "runtime" / "progress"
    values: list[dict[str, Any]] = []
    if not directory.is_dir():
        return values
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and set(value).issubset(ALLOWED_FIELDS):
            values.append({key: item for key, item in value.items() if key in PUBLIC_FIELDS})
    return values


def observed_phases(workflow_dir: Path) -> dict[str, set[str]]:
    path = workflow_dir / "runtime" / "progress" / "events.jsonl"
    phases: dict[str, set[str]] = {}
    if not path.is_file():
        return phases
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"progress event line {line_number} is invalid JSON") from error
        if not isinstance(value, dict) or not set(value).issubset(ALLOWED_FIELDS):
            raise ValueError(f"progress event line {line_number} has unsafe fields")
        node_id = value.get("node_id")
        phase = value.get("phase")
        if not isinstance(node_id, str) or phase not in PHASES:
            raise ValueError(f"progress event line {line_number} has invalid identity or phase")
        phases.setdefault(node_id, set()).add(phase)
    return phases


def validate_completion(
    workflow_dir: Path,
    graph: dict[str, Any],
    workspace_modes: dict[str, str],
) -> list[str]:
    phases = observed_phases(workflow_dir)
    integrity = graph.get("integrity") if isinstance(graph.get("integrity"), dict) else {}
    level = integrity.get("level")
    errors: list[str] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("kind") == "expand" or node.get("status") != "complete":
            continue
        node_id = str(node.get("id"))
        observed = phases.get(node_id, set())
        snapshot_path = workflow_dir / "runtime" / "progress" / f"{node_id}.json"
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            snapshot = None
        if not isinstance(snapshot, dict) or snapshot.get("node_id") != node_id:
            errors.append(f"node {node_id}: missing coordinator terminal progress snapshot")
            current_phase = None
        else:
            current_phase = snapshot.get("phase")
        if "evidence_passed" not in observed:
            errors.append(f"node {node_id}: missing coordinator evidence_passed phase")
        scope = node.get("scope") if isinstance(node.get("scope"), dict) else {}
        if (scope.get("write") or workspace_modes.get(node_id) != "primary") and "scope_accepted" not in observed:
            errors.append(f"node {node_id}: missing coordinator scope_accepted phase")
        if node.get("kind") == "verify" and level in {"medium", "high"} and "independently_verified" not in observed:
            errors.append(f"node {node_id}: missing independent verification phase")
        if node.get("kind") == "verify" and level == "high" and "externally_verified" not in observed:
            errors.append(f"node {node_id}: missing protected external verification phase")
        expected_terminal = (
            {"externally_verified"} if node.get("kind") == "verify" and level == "high"
            else {"independently_verified", "externally_verified"} if node.get("kind") == "verify"
            else {"accepted"}
        )
        if current_phase is not None and current_phase not in expected_terminal:
            errors.append(f"node {node_id}: coordinator terminal progress snapshot is not accepted")
    return errors
