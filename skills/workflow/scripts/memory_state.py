#!/usr/bin/env python3
"""Manage one workflow's shared blackboard memory with CAS and event replay."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


POLICY = "blackboard-event-sourcing-v1"
KINDS = {"fact", "decision", "risk", "question", "learning", "handoff"}
STATUSES = {"active", "resolved", "superseded"}
EVIDENCE_STATES = {"verified", "observed", "inferred", "unverified"}
CONFIDENCE_BY_EVIDENCE = {
    "verified": {"high", "medium"},
    "observed": {"medium", "low"},
    "inferred": {"low"},
    "unverified": {"none"},
}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SECRET_RE = re.compile(r"(?i)(password|api[_-]?key|secret|access[_-]?token)\s*[:=]|-----BEGIN [A-Z ]*PRIVATE KEY-----")
STATE_FIELDS = {"schema_version", "workflow_id", "revision", "graph_digest", "updated_at", "entries"}
ENTRY_FIELDS = {
    "id", "kind", "namespace", "summary", "status", "evidence_state", "confidence",
    "owner_node", "requirement_ids", "relevant_nodes", "artifact_refs", "pivotal",
    "supersedes", "created_revision", "updated_revision",
}
DELTA_ENTRY_FIELDS = ENTRY_FIELDS - {"created_revision", "updated_revision"}
MEMORY_CONFIG = {
    "schema_version": 1,
    "policy": POLICY,
    "state": "memory/state.json",
    "events": "memory/events.jsonl",
    "capsules": "memory/capsules",
}


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
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def invalidate_capsules(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    removed: list[str] = []
    for capsule in path.glob("*.json"):
        if capsule.is_file():
            capsule.unlink()
            removed.append(capsule.name)
    return sorted(removed)


def canonical_graph_digest(graph: dict[str, Any]) -> str:
    semantic = json.loads(json.dumps(graph))
    semantic.pop("lifecycle", None)
    semantic.pop("verification", None)
    for node in semantic.get("nodes", []):
        if not isinstance(node, dict):
            continue
        for field in ("status", "runtime", "retry"):
            node.pop(field, None)
    encoded = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_graph_contract(graph_path: Path) -> None:
    validator = Path(__file__).with_name("validate_graph.py")
    completed = subprocess.run(
        [sys.executable, str(validator), str(graph_path), "--phase", "draft", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise ValueError(f"graph validation failed: {(completed.stdout + completed.stderr).strip()}")


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip() or value.startswith("/") or "\\" in value or "*" in value or "?" in value:
        return None
    normalized = posixpath.normpath(value)
    if normalized in {".", ".."} or normalized.startswith("../"):
        return None
    return str(PurePosixPath(normalized))


def paths_overlap(left: str, right: str) -> bool:
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    shared = min(len(left_parts), len(right_parts))
    return left_parts[:shared] == right_parts[:shared]


def load_workflow(workflow_dir: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    graph_path = workflow_dir / "graph.json"
    graph = load_json(graph_path, "graph.json")
    if not isinstance(graph, dict):
        raise ValueError("graph root must be an object")
    config = graph.get("shared_memory")
    if config != MEMORY_CONFIG:
        raise ValueError(f"graph shared_memory must equal {MEMORY_CONFIG!r}")
    return graph, {
        "graph": graph_path,
        "state": workflow_dir / config["state"],
        "events": workflow_dir / config["events"],
        "capsules": workflow_dir / config["capsules"],
    }


def node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node.get("id"): node for node in graph.get("nodes", []) if isinstance(node, dict) and isinstance(node.get("id"), str)}


def requirement_ids(graph: dict[str, Any]) -> set[str]:
    objective = graph.get("objective") if isinstance(graph.get("objective"), dict) else {}
    return {item.get("id") for item in objective.get("requirements", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}


def add_error(errors: list[str], where: str, message: str) -> None:
    errors.append(f"{where}: {message}")


def resolve_artifact(workflow_dir: Path, repo_root: Path, graph: dict[str, Any], entry: dict[str, Any], artifact: str) -> Path | None:
    if artifact == "memory" or artifact.startswith("memory/"):
        return None
    owner = entry.get("owner_node")
    if owner == "coordinator":
        return workflow_dir / artifact
    node = node_map(graph).get(owner)
    if not node:
        return None
    scope = node.get("scope") if isinstance(node.get("scope"), dict) else {}
    for owned in scope.get("write", []):
        if isinstance(owned, str) and paths_overlap(owned, artifact):
            return repo_root / artifact
    for owned in scope.get("artifacts", []):
        if isinstance(owned, str) and paths_overlap(owned, artifact):
            return workflow_dir / artifact
    return None


def validate_entry(
    entry: Any,
    index: int,
    graph: dict[str, Any],
    workflow_dir: Path,
    repo_root: Path,
    *,
    delta: bool,
    check_artifacts: bool,
) -> list[str]:
    errors: list[str] = []
    where = f"entries[{index}]"
    if not isinstance(entry, dict):
        return [f"{where}: must be an object"]
    expected_fields = DELTA_ENTRY_FIELDS if delta else ENTRY_FIELDS
    missing = sorted(expected_fields - set(entry))
    unknown = sorted(set(entry) - expected_fields)
    if missing:
        add_error(errors, where, f"missing fields {missing!r}")
    if unknown:
        add_error(errors, where, f"unknown fields {unknown!r}")
    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not ID_RE.fullmatch(entry_id):
        add_error(errors, f"{where}.id", "must be a stable identifier")
    if entry.get("kind") not in KINDS:
        add_error(errors, f"{where}.kind", f"must be one of {sorted(KINDS)}")
    namespace = entry.get("namespace")
    if not isinstance(namespace, str) or not namespace.strip() or len(namespace) > 128 or SECRET_RE.search(namespace):
        add_error(errors, f"{where}.namespace", "must be a sanitized non-empty string of at most 128 characters")
    summary = entry.get("summary")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 500 or SECRET_RE.search(summary):
        add_error(errors, f"{where}.summary", "must be sanitized, non-empty, and at most 500 characters")
    if entry.get("status") not in STATUSES:
        add_error(errors, f"{where}.status", f"must be one of {sorted(STATUSES)}")
    evidence_state = entry.get("evidence_state")
    confidence = entry.get("confidence")
    if evidence_state not in EVIDENCE_STATES:
        add_error(errors, f"{where}.evidence_state", "has an unknown state")
    elif confidence not in CONFIDENCE_BY_EVIDENCE[evidence_state]:
        add_error(errors, f"{where}.confidence", f"must be one of {sorted(CONFIDENCE_BY_EVIDENCE[evidence_state])}")
    nodes = node_map(graph)
    owner = entry.get("owner_node")
    if owner != "coordinator" and owner not in nodes:
        add_error(errors, f"{where}.owner_node", "must be coordinator or an existing node")
    known_requirements = requirement_ids(graph)
    for field, known in (("requirement_ids", known_requirements), ("relevant_nodes", set(nodes))):
        values = entry.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) or value not in known for value in values):
            add_error(errors, f"{where}.{field}", "must contain only existing identifiers")
        elif len(values) != len(set(values)):
            add_error(errors, f"{where}.{field}", "contains duplicates")
    if not isinstance(entry.get("pivotal"), bool):
        add_error(errors, f"{where}.pivotal", "must be a boolean")
    supersedes = entry.get("supersedes")
    if supersedes is not None and (not isinstance(supersedes, str) or not ID_RE.fullmatch(supersedes)):
        add_error(errors, f"{where}.supersedes", "must be a stable entry ID or null")
    if not delta:
        for field in ("created_revision", "updated_revision"):
            value = entry.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                add_error(errors, f"{where}.{field}", "must be a non-negative integer")
    refs = entry.get("artifact_refs")
    if not isinstance(refs, list):
        add_error(errors, f"{where}.artifact_refs", "must be a list")
        refs = []
    for ref_index, ref in enumerate(refs):
        ref_where = f"{where}.artifact_refs[{ref_index}]"
        if not isinstance(ref, dict) or set(ref) != {"path", "digest"}:
            add_error(errors, ref_where, "must contain exactly path and digest")
            continue
        artifact = normalized_path(ref.get("path"))
        if artifact is None or artifact != ref.get("path"):
            add_error(errors, f"{ref_where}.path", "must be a normalized explicit relative path")
            continue
        digest = ref.get("digest")
        if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
            add_error(errors, f"{ref_where}.digest", "must be sha256:<64 lowercase hex>")
        resolved = resolve_artifact(workflow_dir, repo_root, graph, entry, artifact)
        if resolved is None:
            add_error(errors, f"{ref_where}.path", "is outside the owner's write/artifact scope or reserved memory")
        elif check_artifacts:
            if not resolved.is_file():
                add_error(errors, f"{ref_where}.path", f"artifact does not exist at {resolved}")
            elif file_digest(resolved) != digest:
                add_error(errors, f"{ref_where}.digest", "does not match the artifact")
    if evidence_state in {"verified", "observed"} and not refs:
        add_error(errors, f"{where}.artifact_refs", f"must contain direct evidence for {evidence_state}")
    return errors


def validate_state(
    state: Any,
    graph: dict[str, Any],
    workflow_dir: Path,
    repo_root: Path,
    *,
    phase: str,
    check_artifacts: bool,
    allow_stale_graph: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["state: root must be an object"]
    if set(state) != STATE_FIELDS:
        add_error(errors, "state", f"must contain exactly {sorted(STATE_FIELDS)!r}")
    if state.get("schema_version") != 1:
        add_error(errors, "state.schema_version", "must equal 1")
    if state.get("workflow_id") != graph.get("workflow_id"):
        add_error(errors, "state.workflow_id", "must match graph workflow_id")
    revision = state.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        add_error(errors, "state.revision", "must be a non-negative integer")
    expected_digest = canonical_graph_digest(graph)
    if not allow_stale_graph and state.get("graph_digest") != expected_digest:
        add_error(errors, "state.graph_digest", "is stale; run bind-graph after validating the graph change")
    if not isinstance(state.get("updated_at"), str) or not state["updated_at"]:
        add_error(errors, "state.updated_at", "must be an ISO timestamp")
    entries = state.get("entries")
    if not isinstance(entries, list):
        add_error(errors, "state.entries", "must be a list")
        return errors
    for index, entry in enumerate(entries):
        errors.extend(validate_entry(entry, index, graph, workflow_dir, repo_root, delta=False, check_artifacts=check_artifacts))
    ids = [entry.get("id") for entry in entries if isinstance(entry, dict)]
    if len(ids) != len(set(ids)):
        add_error(errors, "state.entries", "entry IDs must be unique")
    known_ids = set(ids)
    for entry in entries:
        if isinstance(entry, dict) and entry.get("supersedes") is not None and entry.get("supersedes") not in known_ids:
            # Compaction may archive the target; the append-only log remains authoritative.
            continue
    active_namespaces: dict[tuple[str, str], str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("status") != "active" or entry.get("kind") not in {"decision", "handoff"}:
            continue
        key = (str(entry.get("kind")), str(entry.get("namespace")))
        if key in active_namespaces:
            add_error(errors, "state.entries", f"conflicting active {key[0]} namespace {key[1]!r}")
        else:
            active_namespaces[key] = str(entry.get("id"))
    if phase == "complete":
        unresolved = [entry.get("id") for entry in entries if isinstance(entry, dict) and entry.get("kind") == "question" and entry.get("status") == "active" and entry.get("pivotal") is True]
        if unresolved:
            add_error(errors, "state.entries", f"pivotal questions remain active: {', '.join(map(str, unresolved))}")
    return errors


def read_events(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"cannot read events: {error}") from error
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"events line {line_number}: {error}") from error
        if not isinstance(event, dict):
            raise ValueError(f"events line {line_number}: must be an object")
        events.append(event)
    return events


def replay_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events or events[0].get("type") != "initialized" or events[0].get("revision") != 0:
        raise ValueError("events must start with revision-0 initialized event")
    first = events[0]
    state: dict[str, Any] = {
        "schema_version": 1,
        "workflow_id": first.get("workflow_id"),
        "revision": 0,
        "graph_digest": first.get("graph_digest"),
        "updated_at": first.get("at"),
        "entries": [],
    }
    for event in events[1:]:
        revision = event.get("revision")
        if revision != state["revision"] + 1:
            raise ValueError(f"event revision {revision!r} does not follow {state['revision']}")
        event_type = event.get("type")
        entries = state["entries"]
        by_id = {entry["id"]: entry for entry in entries}
        if event_type == "delta_applied":
            for target in event.get("superseded", []):
                if target not in by_id:
                    raise ValueError(f"event supersedes unknown entry {target}")
                by_id[target]["status"] = "superseded"
                by_id[target]["updated_revision"] = revision
            for target in event.get("resolved", []):
                if target not in by_id:
                    raise ValueError(f"event resolves unknown entry {target}")
                by_id[target]["status"] = "resolved"
                by_id[target]["updated_revision"] = revision
            entries.extend(event.get("added", []))
        elif event_type == "graph_bound":
            state["graph_digest"] = event.get("graph_digest")
        elif event_type == "compacted":
            removed = set(event.get("removed", []))
            state["entries"] = [entry for entry in entries if entry.get("id") not in removed]
        else:
            raise ValueError(f"unknown event type {event_type!r}")
        state["revision"] = revision
        state["updated_at"] = event.get("at")
    return state


def command_init(workflow_dir: Path, repo_root: Path) -> dict[str, Any]:
    graph, paths = load_workflow(workflow_dir)
    validate_graph_contract(paths["graph"])
    state_path = paths["state"]
    events_path = paths["events"]
    if events_path.exists() and events_path.stat().st_size:
        raise ValueError("shared memory is already initialized")
    if state_path.exists():
        existing = load_json(state_path, "memory state")
        if not isinstance(existing, dict) or existing.get("graph_digest") is not None or existing.get("entries") not in ([], None):
            raise ValueError("refusing to overwrite non-template memory state")
    timestamp = now_utc()
    digest = canonical_graph_digest(graph)
    state = {"schema_version": 1, "workflow_id": graph.get("workflow_id"), "revision": 0, "graph_digest": digest, "updated_at": timestamp, "entries": []}
    event = {"type": "initialized", "revision": 0, "workflow_id": graph.get("workflow_id"), "graph_digest": digest, "at": timestamp}
    paths["capsules"].mkdir(parents=True, exist_ok=True)
    atomic_text(events_path, json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    atomic_json(state_path, state)
    return {"workflow_id": graph.get("workflow_id"), "revision": 0, "graph_digest": digest}


def load_initialized(workflow_dir: Path, repo_root: Path, *, allow_stale_graph: bool = False) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path], list[dict[str, Any]]]:
    graph, paths = load_workflow(workflow_dir)
    state = load_json(paths["state"], "memory state")
    events = read_events(paths["events"])
    errors = validate_state(state, graph, workflow_dir, repo_root, phase="active", check_artifacts=False, allow_stale_graph=allow_stale_graph)
    if errors:
        raise ValueError("; ".join(errors))
    replayed = replay_events(events)
    if replayed != state:
        raise ValueError("memory snapshot diverges from append-only event replay")
    return graph, state, paths, events


def all_event_ids(events: list[dict[str, Any]]) -> set[str]:
    return {entry.get("id") for event in events for entry in event.get("added", []) if isinstance(entry, dict) and isinstance(entry.get("id"), str)}


def namespace_allowed(author: str, namespace: str, graph: dict[str, Any]) -> bool:
    if author == "coordinator":
        return True
    node = node_map(graph).get(author, {})
    decisions = (node.get("scope") or {}).get("decisions", []) if isinstance(node.get("scope"), dict) else []
    prefixes = [f"node.{author}", *[value for value in decisions if isinstance(value, str)]]
    return any(namespace == prefix or namespace.startswith(prefix + ".") for prefix in prefixes)


def command_apply(workflow_dir: Path, repo_root: Path, delta_path: Path) -> dict[str, Any]:
    graph, state, paths, events = load_initialized(workflow_dir, repo_root)
    delta = load_json(delta_path, "memory delta")
    if not isinstance(delta, dict) or set(delta) != {"schema_version", "base_revision", "author_node", "add", "supersede", "resolve"}:
        raise ValueError("delta must contain exactly schema_version, base_revision, author_node, add, supersede, resolve")
    if delta.get("schema_version") != 1:
        raise ValueError("delta schema_version must equal 1")
    if delta.get("base_revision") != state["revision"]:
        raise ValueError(f"stale base_revision {delta.get('base_revision')!r}; current revision is {state['revision']}")
    author = delta.get("author_node")
    if author != "coordinator" and author not in node_map(graph):
        raise ValueError("author_node must be coordinator or an existing node")
    added = delta.get("add")
    superseded = delta.get("supersede")
    resolved = delta.get("resolve")
    if not isinstance(added, list) or not isinstance(superseded, list) or not isinstance(resolved, list):
        raise ValueError("add, supersede, and resolve must be lists")
    if any(not isinstance(value, str) for value in superseded + resolved) or len(set(superseded + resolved)) != len(superseded + resolved):
        raise ValueError("supersede and resolve must contain unique entry IDs")
    entry_errors: list[str] = []
    for index, entry in enumerate(added):
        entry_errors.extend(validate_entry(entry, index, graph, workflow_dir, repo_root, delta=True, check_artifacts=True))
        if isinstance(entry, dict):
            if entry.get("status") != "active":
                entry_errors.append(f"entries[{index}].status: newly added entries must be active")
            if entry.get("owner_node") != author:
                entry_errors.append(f"entries[{index}].owner_node: must equal author_node")
            namespace = entry.get("namespace")
            if isinstance(namespace, str) and not namespace_allowed(str(author), namespace, graph):
                entry_errors.append(f"entries[{index}].namespace: author does not own this namespace")
            target = entry.get("supersedes")
            if target is not None and target not in superseded:
                entry_errors.append(f"entries[{index}].supersedes: target must also appear in delta.supersede")
    if entry_errors:
        raise ValueError("; ".join(entry_errors))
    existing = {entry["id"]: entry for entry in state["entries"]}
    historical_ids = all_event_ids(events)
    new_ids = [entry.get("id") for entry in added if isinstance(entry, dict)]
    if len(new_ids) != len(set(new_ids)) or any(entry_id in historical_ids for entry_id in new_ids):
        raise ValueError("new entry IDs must be unique across event history")
    for target in superseded + resolved:
        if target not in existing or existing[target].get("status") != "active":
            raise ValueError(f"target {target} is not an active entry")
        if author != "coordinator" and existing[target].get("owner_node") != author:
            raise ValueError(f"author may not change entry {target} owned by another node")
    revision = state["revision"] + 1
    timestamp = now_utc()
    for target in superseded:
        existing[target]["status"] = "superseded"
        existing[target]["updated_revision"] = revision
    for target in resolved:
        existing[target]["status"] = "resolved"
        existing[target]["updated_revision"] = revision
    materialized: list[dict[str, Any]] = []
    for entry in added:
        value = dict(entry)
        value["created_revision"] = revision
        value["updated_revision"] = revision
        materialized.append(value)
    state["entries"].extend(materialized)
    state["revision"] = revision
    state["updated_at"] = timestamp
    errors = validate_state(state, graph, workflow_dir, repo_root, phase="active", check_artifacts=True)
    if errors:
        raise ValueError("; ".join(errors))
    event = {"type": "delta_applied", "revision": revision, "at": timestamp, "author_node": author, "added": materialized, "superseded": superseded, "resolved": resolved}
    append_event(paths["events"], event)
    atomic_json(paths["state"], state)
    invalidated = invalidate_capsules(paths["capsules"])
    return {"revision": revision, "added": new_ids, "superseded": superseded, "resolved": resolved, "invalidated_capsules": invalidated}


def command_bind(workflow_dir: Path, repo_root: Path) -> dict[str, Any]:
    graph, state, paths, _ = load_initialized(workflow_dir, repo_root, allow_stale_graph=True)
    validate_graph_contract(paths["graph"])
    digest = canonical_graph_digest(graph)
    if state.get("graph_digest") == digest:
        return {"revision": state["revision"], "graph_digest": digest, "changed": False}
    revision = state["revision"] + 1
    timestamp = now_utc()
    event = {"type": "graph_bound", "revision": revision, "at": timestamp, "graph_digest": digest}
    state.update(revision=revision, graph_digest=digest, updated_at=timestamp)
    append_event(paths["events"], event)
    atomic_json(paths["state"], state)
    invalidated = invalidate_capsules(paths["capsules"])
    return {"revision": revision, "graph_digest": digest, "changed": True, "invalidated_capsules": invalidated}


def command_compact(workflow_dir: Path, repo_root: Path) -> dict[str, Any]:
    graph, state, paths, _ = load_initialized(workflow_dir, repo_root)
    removed = [entry["id"] for entry in state["entries"] if entry.get("status") in {"resolved", "superseded"}]
    if not removed:
        return {"revision": state["revision"], "removed": []}
    revision = state["revision"] + 1
    timestamp = now_utc()
    state["entries"] = [entry for entry in state["entries"] if entry["id"] not in set(removed)]
    state.update(revision=revision, updated_at=timestamp)
    event = {"type": "compacted", "revision": revision, "at": timestamp, "removed": removed}
    append_event(paths["events"], event)
    atomic_json(paths["state"], state)
    invalidated = invalidate_capsules(paths["capsules"])
    return {"revision": revision, "removed": removed, "invalidated_capsules": invalidated}


def ancestors(node_id: str, graph: dict[str, Any]) -> set[str]:
    nodes = node_map(graph)
    found: set[str] = set()
    stack = list(nodes.get(node_id, {}).get("depends_on", []))
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        stack.extend(nodes.get(current, {}).get("depends_on", []))
    return found


def command_view(workflow_dir: Path, repo_root: Path, node_id: str, max_entries: int, max_chars: int, output: Path | None) -> dict[str, Any]:
    graph, state, paths, _ = load_initialized(workflow_dir, repo_root)
    nodes = node_map(graph)
    if node_id not in nodes:
        raise ValueError(f"unknown node {node_id}")
    node = nodes[node_id]
    covers = set(node.get("covers", []))
    dependency_nodes = ancestors(node_id, graph)
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for entry in state["entries"]:
        if entry.get("status") != "active":
            continue
        score = 0
        if entry.get("pivotal"):
            score += 100
        if node_id in entry.get("relevant_nodes", []):
            score += 80
        if covers & set(entry.get("requirement_ids", [])):
            score += 70
        if entry.get("owner_node") == node_id:
            score += 60
        if entry.get("owner_node") in dependency_nodes:
            score += 50
        if score:
            ranked.append((-score, str(entry.get("id")), entry))
    ranked.sort(key=lambda item: (item[0], item[1]))
    selected: list[dict[str, Any]] = []
    used_chars = 0
    for _, _, entry in ranked:
        encoded = json.dumps(entry, separators=(",", ":"), ensure_ascii=False)
        if len(selected) >= max_entries or used_chars + len(encoded) > max_chars:
            continue
        selected.append(entry)
        used_chars += len(encoded)
    capsule = {
        "schema_version": 1,
        "workflow_id": graph.get("workflow_id"),
        "memory_revision": state["revision"],
        "graph_digest": state["graph_digest"],
        "node_id": node_id,
        "entries": selected,
        "omitted_count": len(ranked) - len(selected),
        "character_count": used_chars,
    }
    target = output or paths["capsules"] / f"{node_id}.json"
    if not target.resolve().is_relative_to(paths["capsules"].resolve()):
        raise ValueError("capsule output must remain inside memory/capsules")
    atomic_json(target, capsule)
    return capsule


def validate_capsules(path: Path, state: dict[str, Any], graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not path.is_dir():
        return ["memory/capsules: directory is missing"]
    for capsule_path in path.glob("*.json"):
        try:
            capsule = load_json(capsule_path, f"capsule {capsule_path.name}")
        except ValueError as error:
            errors.append(str(error))
            continue
        if not isinstance(capsule, dict):
            errors.append(f"capsule {capsule_path.name}: root must be an object")
            continue
        if capsule.get("memory_revision") != state.get("revision") or capsule.get("graph_digest") != state.get("graph_digest"):
            errors.append(f"capsule {capsule_path.name}: stale revision or graph digest")
        if capsule.get("node_id") not in node_map(graph):
            errors.append(f"capsule {capsule_path.name}: unknown node")
    return errors


def command_validate(workflow_dir: Path, repo_root: Path, phase: str, check_artifacts: bool) -> dict[str, Any]:
    graph, state, paths, events = load_initialized(workflow_dir, repo_root)
    errors = validate_state(state, graph, workflow_dir, repo_root, phase=phase, check_artifacts=check_artifacts)
    errors.extend(validate_capsules(paths["capsules"], state, graph))
    if errors:
        raise ValueError("; ".join(errors))
    return {"valid": True, "phase": phase, "revision": state["revision"], "entries": len(state["entries"]), "events": len(events)}


def command_replay(workflow_dir: Path, repo_root: Path, check: bool) -> dict[str, Any]:
    graph, paths = load_workflow(workflow_dir)
    events = read_events(paths["events"])
    replayed = replay_events(events)
    if check:
        current = load_json(paths["state"], "memory state")
        if replayed != current:
            raise ValueError("memory snapshot diverges from event replay")
    else:
        errors = validate_state(replayed, graph, workflow_dir, repo_root, phase="active", check_artifacts=False)
        if errors:
            raise ValueError("; ".join(errors))
        atomic_json(paths["state"], replayed)
    return {"revision": replayed["revision"], "entries": len(replayed["entries"]), "matched": check}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "bind-graph", "compact"):
        subparsers.add_parser(name).add_argument("workflow_dir", type=Path)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("workflow_dir", type=Path)
    validate_parser.add_argument("--phase", choices=("active", "complete"), default="active")
    validate_parser.add_argument("--check-artifacts", action="store_true")
    apply_parser = subparsers.add_parser("apply-delta")
    apply_parser.add_argument("workflow_dir", type=Path)
    apply_parser.add_argument("delta", type=Path)
    view_parser = subparsers.add_parser("view")
    view_parser.add_argument("workflow_dir", type=Path)
    view_parser.add_argument("--node", required=True)
    view_parser.add_argument("--max-entries", type=int, default=20)
    view_parser.add_argument("--max-chars", type=int, default=6000)
    view_parser.add_argument("--output", type=Path)
    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("workflow_dir", type=Path)
    replay_parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    workflow_dir = args.workflow_dir.resolve()
    repo_root = args.repo_root.resolve()
    try:
        if args.command == "init":
            result = command_init(workflow_dir, repo_root)
        elif args.command == "bind-graph":
            result = command_bind(workflow_dir, repo_root)
        elif args.command == "compact":
            result = command_compact(workflow_dir, repo_root)
        elif args.command == "apply-delta":
            result = command_apply(workflow_dir, repo_root, args.delta.resolve())
        elif args.command == "view":
            if args.max_entries <= 0 or args.max_chars < 512:
                raise ValueError("view limits require max_entries > 0 and max_chars >= 512")
            result = command_view(workflow_dir, repo_root, args.node, args.max_entries, args.max_chars, args.output.resolve() if args.output else None)
        elif args.command == "validate":
            result = command_validate(workflow_dir, repo_root, args.phase, args.check_artifacts)
        else:
            result = command_replay(workflow_dir, repo_root, args.check)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
