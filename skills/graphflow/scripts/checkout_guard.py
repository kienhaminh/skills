#!/usr/bin/env python3
"""Pin the primary checkout and fail closed on concurrent or escaped mutations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from executor_common import append_event, atomic_json, canonical_graph_digest, json_digest, load_json, now_utc
import workspace_manager


POLICY = "primary-checkout-baseline-v1"
BASELINE_PATH = "runtime/checkout-baseline.json"
STATUS_PATH = "runtime/checkout-status.json"
EVENTS_PATH = "runtime/checkout-events.jsonl"
CONFIG_FIELDS = {
    "schema_version", "policy", "status", "baseline", "current", "events",
    "baseline_digest", "request_id", "failure", "updated_at",
}
STATUSES = {"uninitialized", "clear", "waiting_approval", "blocked"}


def default_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy": POLICY,
        "status": "uninitialized",
        "baseline": BASELINE_PATH,
        "current": STATUS_PATH,
        "events": EVENTS_PATH,
        "baseline_digest": None,
        "request_id": None,
        "failure": None,
        "updated_at": None,
    }


def validate_config(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != CONFIG_FIELDS:
        raise ValueError(f"runtime.checkout_guard must contain exactly {sorted(CONFIG_FIELDS)!r}")
    if value.get("schema_version") != 1 or value.get("policy") != POLICY:
        raise ValueError("runtime.checkout_guard has an unsupported schema or policy")
    if value.get("status") not in STATUSES:
        raise ValueError("runtime.checkout_guard status is invalid")
    for field in ("baseline", "current", "events"):
        item = value.get(field)
        if not isinstance(item, str) or not item or Path(item).is_absolute() or ".." in Path(item).parts:
            raise ValueError(f"runtime.checkout_guard.{field} must be a safe relative path")
    if value.get("request_id") is not None and not isinstance(value.get("request_id"), str):
        raise ValueError("runtime.checkout_guard.request_id must be null or a string")
    baseline_digest = value.get("baseline_digest")
    if baseline_digest is not None and (not isinstance(baseline_digest, str) or not baseline_digest.startswith("sha256:")):
        raise ValueError("runtime.checkout_guard.baseline_digest must be null or a SHA-256 digest")
    if value.get("failure") is not None and not isinstance(value.get("failure"), str):
        raise ValueError("runtime.checkout_guard.failure must be null or a string")
    return dict(value)


def git_bytes(repo: Path, *args: str, check: bool = True) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=False,
    )
    if check and completed.returncode:
        detail = (completed.stderr or completed.stdout).decode("utf-8", errors="replace").strip()
        raise ValueError(detail or f"git {' '.join(args)} failed")
    return completed.stdout


def file_digest(path: Path) -> tuple[str, str]:
    if path.is_symlink():
        content = os.readlink(path).encode("utf-8", errors="surrogateescape")
        return "symlink", "sha256:" + hashlib.sha256(content).hexdigest()
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return "file", "sha256:" + digest.hexdigest()
    if path.is_dir():
        head = git_bytes(path, "rev-parse", "HEAD", check=False).strip()
        status = git_bytes(path, "status", "--porcelain=v1", "-z", check=False)
        return "directory", "sha256:" + hashlib.sha256(head + b"\0" + status).hexdigest()
    return "missing", "sha256:" + hashlib.sha256(b"").hexdigest()


def excluded_prefix(workflow_dir: Path, repo: Path) -> str | None:
    try:
        relative = workflow_dir.resolve().relative_to(repo.resolve())
    except ValueError:
        return None
    return relative.as_posix().rstrip("/")


def excluded(path: str, prefix: str | None) -> bool:
    return bool(prefix and (path == prefix or path.startswith(prefix + "/")))


def index_digest(repo: Path, relative: str) -> str | None:
    value = git_bytes(repo, "rev-parse", "--verify", f":{relative}", check=False).strip()
    return "sha256:" + hashlib.sha256(value).hexdigest() if value else None


def logical_git_metadata_digest(repo: Path) -> str:
    """Hash semantic Git controls without volatile index stat-cache bytes."""
    common = workspace_manager.common_dir(repo)
    local = workspace_manager.git_dir(repo)
    candidates = [
        common / "config",
        common / "info" / "exclude",
        common / "info" / "attributes",
        local / "config.worktree",
    ]
    hooks = common / "hooks"
    if hooks.is_dir():
        candidates.extend(sorted(item for item in hooks.rglob("*") if item.is_file() or item.is_symlink()))
    records: list[dict[str, str]] = []
    for candidate in candidates:
        label = f"common:{candidate.relative_to(common)}" if candidate.is_relative_to(common) else f"local:{candidate.name}"
        if candidate.is_symlink():
            kind = "symlink"
            content = os.readlink(candidate).encode("utf-8", errors="surrogateescape")
        elif candidate.is_file():
            kind = "file"
            content = candidate.read_bytes()
        else:
            kind = "missing"
            content = b""
        records.append({"path": label, "kind": kind, "digest": "sha256:" + hashlib.sha256(content).hexdigest()})
    records.append({
        "path": "logical:index",
        "kind": "git-index",
        "digest": "sha256:" + hashlib.sha256(git_bytes(repo, "ls-files", "--stage", "-z")).hexdigest(),
    })
    return json_digest(records)


def changed_entries(repo: Path, workflow_dir: Path) -> list[dict[str, Any]]:
    prefix = excluded_prefix(workflow_dir, repo)
    tracked = {
        item.decode("utf-8", errors="surrogateescape")
        for item in git_bytes(repo, "diff", "--name-only", "-z", "HEAD", "--").split(b"\0") if item
    }
    untracked = {
        item.decode("utf-8", errors="surrogateescape")
        for item in git_bytes(repo, "ls-files", "--others", "--exclude-standard", "-z", "--").split(b"\0") if item
    }
    entries: list[dict[str, Any]] = []
    for relative in sorted((tracked | untracked), key=lambda value: value.encode("utf-8", errors="surrogateescape")):
        if excluded(relative, prefix):
            continue
        kind, digest = file_digest(repo / relative)
        entries.append({
            "path": relative,
            "change": "untracked" if relative in untracked else "tracked-change",
            "kind": kind,
            "worktree_digest": digest,
            "index_digest": None if relative in untracked else index_digest(repo, relative),
        })
    return entries


def declared_scopes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    scopes: list[dict[str, Any]] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("kind") == "expand" or not isinstance(node.get("id"), str):
            continue
        scope = node.get("scope") if isinstance(node.get("scope"), dict) else {}
        writes = sorted(value.rstrip("/") for value in scope.get("write", []) if isinstance(value, str) and value)
        executor = node.get("executor") if isinstance(node.get("executor"), dict) else {}
        scopes.append({"node_id": node["id"], "executor": executor.get("spec"), "write": writes})
    return scopes


def owners_for(path: str, scopes: list[dict[str, Any]]) -> list[str]:
    owners: list[str] = []
    for scope in scopes:
        if any(path == root or path.startswith(root + "/") for root in scope.get("write", [])):
            owners.append(str(scope["node_id"]))
    return sorted(owners)


def checkout_state(workflow_dir: Path, repo_root: Path, graph: dict[str, Any]) -> dict[str, Any]:
    repo = workspace_manager.repository_root(repo_root)
    entries = changed_entries(repo, workflow_dir)
    semantic = {
        "repo_root": str(repo),
        "branch": workspace_manager.branch(repo),
        "head_sha": workspace_manager.head(repo),
        "git_metadata_digest": logical_git_metadata_digest(repo),
        "entries": entries,
    }
    return {
        "schema_version": 1,
        "workflow_id": graph.get("workflow_id"),
        "policy": POLICY,
        **semantic,
        "state_digest": json_digest(semantic),
        "captured_at": now_utc(),
    }


def baseline_from(state: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    return {
        **state,
        "graph_digest": canonical_graph_digest(graph),
        "declared_scopes": declared_scopes(graph),
    }


def entry_map(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["path"]): item for item in value.get("entries", []) if isinstance(item, dict) and isinstance(item.get("path"), str)}


def diff_checkout(baseline: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    scopes = baseline.get("declared_scopes") if isinstance(baseline.get("declared_scopes"), list) else []
    before = entry_map(baseline)
    after = entry_map(current)
    changes: list[dict[str, Any]] = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) == after.get(path):
            continue
        kind = "added" if path not in before else "restored" if path not in after else "modified"
        changes.append({"path": path, "change": kind, "declared_owners": owners_for(path, scopes)})
    return changes


def status_snapshot(baseline: dict[str, Any], current: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "workflow_id": baseline.get("workflow_id"),
        "policy": POLICY,
        "status": status,
        "baseline_state_digest": baseline.get("state_digest"),
        "current_state_digest": current.get("state_digest"),
        "baseline_dirty_paths": len(baseline.get("entries", [])),
        "current_dirty_paths": len(current.get("entries", [])),
        "branch_changed": baseline.get("branch") != current.get("branch"),
        "head_changed": baseline.get("head_sha") != current.get("head_sha"),
        "git_metadata_changed": baseline.get("git_metadata_digest") != current.get("git_metadata_digest"),
        "changes": diff_checkout(baseline, current),
        "checked_at": now_utc(),
    }


def request_surface(graph: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    nodes = [str(node["id"]) for node in graph.get("nodes", []) if isinstance(node, dict) and node.get("kind") != "expand" and isinstance(node.get("id"), str)]
    change_labels = [item["path"] for item in snapshot["changes"]]
    controls = []
    if snapshot["branch_changed"]:
        controls.append("branch")
    if snapshot["head_changed"]:
        controls.append("HEAD")
    if snapshot["git_metadata_changed"]:
        controls.append("Git metadata/index")
    summary = ", ".join(change_labels[:8])
    if len(change_labels) > 8:
        summary += f", and {len(change_labels) - 8} more"
    if controls:
        summary = "; ".join(filter(None, [summary, "changed " + ", ".join(controls)]))
    triage = {
        "blocking_scope": "workflow",
        "impacts": ["irreversible_action"],
        "affected_nodes": nodes,
        "no_safe_default_reason": "Adopting an unexplained primary-checkout state could hide concurrent user edits or an executor escape.",
        "resolution_mode": "resume",
        "request_graph_digest": canonical_graph_digest(graph),
        "authority_capabilities": [],
        "checkout_baseline_digest": snapshot["baseline_state_digest"],
        "checkout_state_digest": snapshot["current_state_digest"],
        "checkout_changes": snapshot["changes"],
        "checkout_controls": controls,
    }
    return {
        "question": f"Primary checkout drift detected ({summary or 'state digest changed'}). Adopt this exact observed state as the new baseline and resume?",
        "alternatives": ["Approve this exact digest and resume", "Reject, then restore or reconcile the primary checkout externally"],
        "risks": [
            "Approval accepts every listed path and Git-control change as trusted concurrent state.",
            "Rejection keeps dispatch and Ship delivery blocked until the checkout returns to the pinned baseline.",
        ],
        "triage": triage,
    }


def store_request(workflow_dir: Path, graph: dict[str, Any], snapshot: dict[str, Any]) -> tuple[str, Path]:
    surface = request_surface(graph, snapshot)
    digest = json_digest(surface)
    request_id = f"checkout-guard-{snapshot['current_state_digest'].split(':', 1)[1][:12]}"
    path = workflow_dir / "runtime" / "requests" / f"{request_id}.json"
    value = {
        "schema_version": 2,
        "request_id": request_id,
        "digest": digest,
        "node_id": None,
        "broker": "checkout_guard",
        "status": "pending",
        **surface,
        "created_at": now_utc(),
        "response": None,
    }
    if path.is_file():
        existing = load_json(path, "checkout guard request")
        if not isinstance(existing, dict) or existing.get("digest") != digest:
            raise ValueError("checkout guard request ID was reused with a different decision surface")
        return request_id, path
    atomic_json(path, value)
    return request_id, path


def supersede_request(workflow_dir: Path, request_id: str | None, reason: str) -> None:
    if not request_id:
        return
    path = workflow_dir / "runtime" / "requests" / f"{request_id}.json"
    if not path.is_file():
        return
    value = load_json(path, "checkout guard request")
    if isinstance(value, dict) and value.get("status") in {"pending", "approved", "rejected"}:
        value["status"] = "superseded"
        value["superseded_at"] = now_utc()
        value["invalidated_reason"] = reason
        atomic_json(path, value)


def runtime_config(workflow_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = workflow_dir / "runtime.json"
    runtime = load_json(path, "runtime")
    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object")
    raw = runtime.get("checkout_guard")
    config = default_config() if raw is None else validate_config(raw)
    return runtime, config


def save_config(workflow_dir: Path, runtime: dict[str, Any], config: dict[str, Any]) -> None:
    config["updated_at"] = now_utc()
    runtime["checkout_guard"] = validate_config(config)
    atomic_json(workflow_dir / "runtime.json", runtime)


def set_config(config: dict[str, Any], status: str, request_id: str | None = None, failure: str | None = None) -> None:
    config.update(status=status, request_id=request_id, failure=failure)


def advance(workflow_dir: Path, repo_root: Path) -> dict[str, Any]:
    workflow_dir = workflow_dir.resolve()
    graph = load_json(workflow_dir / "graph.json", "graph")
    if not isinstance(graph, dict):
        raise ValueError("graph must be an object")
    runtime, config = runtime_config(workflow_dir)
    baseline_path = workflow_dir / config["baseline"]
    status_path = workflow_dir / config["current"]
    events_path = workflow_dir / config["events"]
    current = checkout_state(workflow_dir, repo_root, graph)

    if not baseline_path.is_file():
        prior_results = sorted((workflow_dir / "runtime" / "results").glob("*.json")) if (workflow_dir / "runtime" / "results").is_dir() else []
        if prior_results:
            raise ValueError("cannot establish an initial checkout baseline after durable node results exist; inspect/reframe the workflow before resume")
        baseline = baseline_from(current, graph)
        atomic_json(baseline_path, baseline)
        snapshot = status_snapshot(baseline, current, "clear")
        atomic_json(status_path, snapshot)
        config["baseline_digest"] = json_digest(baseline)
        set_config(config, "clear")
        save_config(workflow_dir, runtime, config)
        append_event(events_path, {"type": "baseline_created", "at": now_utc(), "state_digest": current["state_digest"], "dirty_paths": len(current["entries"])})
        return snapshot

    baseline = load_json(baseline_path, "checkout baseline")
    if not isinstance(baseline, dict) or baseline.get("policy") != POLICY or baseline.get("workflow_id") != graph.get("workflow_id"):
        raise ValueError("checkout baseline identity or policy does not match this workflow")
    if config.get("baseline_digest") != json_digest(baseline):
        raise ValueError("checkout baseline digest does not match runtime.checkout_guard; refuse implicit rebaseline")
    same_state = baseline.get("state_digest") == current.get("state_digest")
    current_graph_digest = canonical_graph_digest(graph)

    if same_state:
        if config.get("request_id"):
            supersede_request(workflow_dir, config["request_id"], "primary checkout returned to the pinned baseline")
        if baseline.get("graph_digest") != current_graph_digest:
            baseline["graph_digest"] = current_graph_digest
            baseline["declared_scopes"] = declared_scopes(graph)
            baseline["captured_at"] = now_utc()
            atomic_json(baseline_path, baseline)
            config["baseline_digest"] = json_digest(baseline)
            append_event(events_path, {"type": "scope_binding_refreshed", "at": now_utc(), "graph_digest": current_graph_digest})
        snapshot = status_snapshot(baseline, current, "clear")
        atomic_json(status_path, snapshot)
        set_config(config, "clear")
        save_config(workflow_dir, runtime, config)
        return snapshot

    snapshot = status_snapshot(baseline, current, "waiting_approval")
    existing_request_id = config.get("request_id")
    request: dict[str, Any] | None = None
    if existing_request_id:
        request_path = workflow_dir / "runtime" / "requests" / f"{existing_request_id}.json"
        if request_path.is_file():
            loaded = load_json(request_path, "checkout guard request")
            request = loaded if isinstance(loaded, dict) else None
    triage = request.get("triage") if isinstance(request, dict) and isinstance(request.get("triage"), dict) else {}
    exact_request = (
        request is not None
        and triage.get("checkout_baseline_digest") == snapshot["baseline_state_digest"]
        and triage.get("checkout_state_digest") == snapshot["current_state_digest"]
        and triage.get("request_graph_digest") == current_graph_digest
    )

    if exact_request and request.get("status") == "approved":
        adopted = baseline_from(current, graph)
        atomic_json(baseline_path, adopted)
        config["baseline_digest"] = json_digest(adopted)
        request["status"] = "consumed"
        request["consumed_at"] = now_utc()
        atomic_json(workflow_dir / "runtime" / "requests" / f"{existing_request_id}.json", request)
        snapshot = status_snapshot(adopted, current, "clear")
        atomic_json(status_path, snapshot)
        set_config(config, "clear")
        save_config(workflow_dir, runtime, config)
        append_event(events_path, {"type": "baseline_adopted", "at": now_utc(), "request_id": existing_request_id, "state_digest": current["state_digest"]})
        return snapshot

    if exact_request and request.get("status") == "rejected":
        snapshot["status"] = "blocked"
        atomic_json(status_path, snapshot)
        set_config(config, "blocked", existing_request_id, "User rejected adoption of the exact observed primary-checkout state.")
        save_config(workflow_dir, runtime, config)
        return snapshot

    if existing_request_id and not exact_request:
        supersede_request(workflow_dir, existing_request_id, "checkout or semantic graph changed after the request was issued")
        append_event(events_path, {"type": "request_superseded", "at": now_utc(), "request_id": existing_request_id, "state_digest": current["state_digest"]})
    request_id, _ = store_request(workflow_dir, graph, snapshot)
    atomic_json(status_path, snapshot)
    set_config(config, "waiting_approval", request_id, "Primary checkout changed after the pinned baseline.")
    save_config(workflow_dir, runtime, config)
    if request_id != existing_request_id:
        append_event(events_path, {"type": "mutation_detected", "at": now_utc(), "request_id": request_id, "state_digest": current["state_digest"], "changes": snapshot["changes"], "branch_changed": snapshot["branch_changed"], "head_changed": snapshot["head_changed"], "git_metadata_changed": snapshot["git_metadata_changed"]})
    return snapshot


def projection(workflow_dir: Path) -> dict[str, Any]:
    runtime, config = runtime_config(workflow_dir.resolve())
    del runtime
    path = workflow_dir.resolve() / config["current"]
    if not path.is_file():
        return {
            "schema_version": 1,
            "policy": POLICY,
            "status": config["status"],
            "baseline_dirty_paths": None,
            "current_dirty_paths": None,
            "branch_changed": False,
            "head_changed": False,
            "git_metadata_changed": False,
            "changes": [],
            "checked_at": None,
        }
    value = load_json(path, "checkout guard status")
    if not isinstance(value, dict):
        raise ValueError("checkout guard status must be an object")
    allowed = {
        "schema_version", "workflow_id", "policy", "status", "baseline_state_digest", "current_state_digest",
        "baseline_dirty_paths", "current_dirty_paths", "branch_changed", "head_changed", "git_metadata_changed", "changes", "checked_at",
    }
    return {key: value[key] for key in allowed if key in value}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "check", "inspect"):
        sub = subparsers.add_parser(command)
        sub.add_argument("workflow_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            result = projection(args.workflow_dir)
        else:
            result = advance(args.workflow_dir, args.repo_root.resolve())
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "clear" else 2


if __name__ == "__main__":
    raise SystemExit(main())
