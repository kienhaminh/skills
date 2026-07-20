#!/usr/bin/env python3
"""Provision and verify Graphflow workspaces without trusting worker self-report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from executor_common import atomic_json, json_digest, load_json, node_map, now_utc


MODES = {"primary", "worktree", "integration", "verifier"}
WORKSPACE_FIELDS = {"mode", "ref", "subdir"}
ENTRY_FIELDS = {
    "workspace_id", "node_id", "mode", "path", "branch", "base_sha", "head_sha",
    "source_ref", "status", "workflow_owned", "allocations", "checkpoint_sha", "patch_digest", "updated_at",
}
REGISTRY_FIELDS = {"schema_version", "workflow_id", "repo_root", "repo_common_dir", "entries"}
SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")


def git(repo: Path, *args: str, check: bool = True, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False, env=env,
    )
    if check and completed.returncode:
        raise ValueError((completed.stderr or completed.stdout).strip() or f"git {' '.join(args)} failed")
    return completed.stdout


def git_identity_env() -> dict[str, str]:
    value = os.environ.copy()
    value.update({
        "GIT_AUTHOR_NAME": "Graphflow", "GIT_AUTHOR_EMAIL": "graphflow@local.invalid",
        "GIT_COMMITTER_NAME": "Graphflow", "GIT_COMMITTER_EMAIL": "graphflow@local.invalid",
    })
    return value


def repository_root(path: Path) -> Path:
    output = git(path, "rev-parse", "--show-toplevel").strip()
    if not output:
        raise ValueError(f"not a Git repository: {path}")
    return Path(output).resolve()


def common_dir(path: Path) -> Path:
    value = git(path, "rev-parse", "--git-common-dir").strip()
    candidate = Path(value)
    return (path / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()


def head(path: Path) -> str:
    return git(path, "rev-parse", "HEAD").strip()


def branch(path: Path) -> str:
    value = git(path, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).strip()
    return value or "(detached)"


def changed_files(path: Path) -> list[str]:
    tracked = git(path, "diff", "--name-only", "-z", "HEAD")
    untracked = git(path, "ls-files", "--others", "--exclude-standard", "-z")
    return sorted({item for item in (tracked + untracked).split("\0") if item})


def refs_digest(path: Path) -> str:
    value = git(path, "for-each-ref", "--format=%(refname)%00%(objectname)")
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def git_dir(path: Path) -> Path:
    value = Path(git(path, "rev-parse", "--git-dir").strip())
    return value.resolve() if value.is_absolute() else (path / value).resolve()


def git_metadata_digest(path: Path) -> str:
    """Pin mutable Git control files while ignoring objects and coordinator worktree records."""
    common = common_dir(path)
    local = git_dir(path)
    candidates = [
        common / "config", common / "info" / "exclude", common / "info" / "attributes",
        local / "HEAD", local / "index", local / "config.worktree",
    ]
    hooks = common / "hooks"
    if hooks.is_dir():
        candidates.extend(sorted(item for item in hooks.rglob("*") if item.is_file() or item.is_symlink()))
    records: list[dict[str, str]] = []
    for candidate in candidates:
        label = f"common:{candidate.relative_to(common)}" if candidate.is_relative_to(common) else f"local:{candidate.name}"
        if candidate.is_symlink():
            kind = "symlink"
            content = os.readlink(candidate).encode("utf-8")
        elif candidate.is_file():
            kind = "file"
            content = candidate.read_bytes()
        else:
            kind = "missing"
            content = b""
        records.append({"path": label, "kind": kind, "digest": "sha256:" + hashlib.sha256(content).hexdigest()})
    return json_digest(records)


def workspace_contract(spec: dict[str, Any]) -> dict[str, str]:
    value = spec.get("workspace")
    if not isinstance(value, dict) or set(value) != WORKSPACE_FIELDS:
        raise ValueError(f"executor workspace must contain exactly {sorted(WORKSPACE_FIELDS)!r}")
    if value.get("mode") not in MODES:
        raise ValueError("executor workspace mode is invalid")
    if not isinstance(value.get("ref"), str) or not value["ref"]:
        raise ValueError("executor workspace ref must be non-empty")
    subdir = value.get("subdir")
    if not isinstance(subdir, str) or not subdir or Path(subdir).is_absolute() or ".." in Path(subdir).parts:
        raise ValueError("executor workspace subdir must be a safe relative path")
    return value


def registry_path(workflow_dir: Path) -> Path:
    return workflow_dir / "runtime" / "workspaces.json"


def load_registry(workflow_dir: Path, workflow_id: str | None = None) -> dict[str, Any]:
    value = load_json(registry_path(workflow_dir), "workspace registry")
    if not isinstance(value, dict) or set(value) != REGISTRY_FIELDS:
        raise ValueError(f"workspace registry must contain exactly {sorted(REGISTRY_FIELDS)!r}")
    if value.get("schema_version") != 1:
        raise ValueError("workspace registry schema_version must equal 1")
    if workflow_id is not None and value.get("workflow_id") != workflow_id:
        raise ValueError("workspace registry workflow_id mismatch")
    entries = value.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("workspace registry entries must be an object")
    for key, entry in entries.items():
        if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS or entry.get("workspace_id") != key:
            raise ValueError(f"workspace registry entry {key!r} is invalid")
        if entry.get("mode") not in MODES or not isinstance(entry.get("allocations"), dict):
            raise ValueError(f"workspace registry entry {key!r} has invalid mode or allocations")
    validate_allocations(value)
    return value


def validate_allocations(registry: dict[str, Any]) -> None:
    """Reject imported registries that assign a parallel resource twice."""
    seen: dict[tuple[str, str], str] = {}
    for ref, entry in registry["entries"].items():
        allocations = entry["allocations"]
        required = {"slot", "port_offset", "database_suffix", "compose_project", "cache_dir", "log_dir"}
        if set(allocations) != required:
            raise ValueError(f"workspace registry entry {ref!r} has invalid allocation fields")
        for field in ("slot", "port_offset", "database_suffix", "compose_project", "cache_dir", "log_dir"):
            value = allocations.get(field)
            if value is None and field in {"compose_project", "cache_dir", "log_dir"}:
                continue
            if field in {"slot", "port_offset"}:
                valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
            else:
                valid = isinstance(value, str) and bool(value)
            if not valid:
                raise ValueError(f"workspace registry entry {ref!r} has invalid allocation {field!r}")
            key = (field, str(value))
            owner = seen.get(key)
            if owner is not None:
                raise ValueError(f"workspace allocation collision for {field} between {owner!r} and {ref!r}")
            seen[key] = ref


def write_registry(workflow_dir: Path, registry: dict[str, Any]) -> None:
    atomic_json(registry_path(workflow_dir), registry)


def default_entry(node_id: str, contract: dict[str, str], slot: int) -> dict[str, Any]:
    mode = contract["mode"]
    return {
        "workspace_id": contract["ref"],
        "node_id": node_id,
        "mode": mode,
        "path": None,
        "branch": None,
        "base_sha": None,
        "head_sha": None,
        "source_ref": None,
        "status": "unprovisioned",
        "workflow_owned": mode != "primary",
        "allocations": {
            "slot": slot,
            "port_offset": slot * 100,
            "database_suffix": f"_test_{node_id.lower()}",
            "compose_project": None,
            "cache_dir": None,
            "log_dir": None,
        },
        "checkpoint_sha": None,
        "patch_digest": None,
        "updated_at": None,
    }


def initialize(workflow_dir: Path) -> dict[str, Any]:
    graph = load_json(workflow_dir / "graph.json", "graph")
    if not isinstance(graph, dict) or graph.get("version") != 3:
        raise ValueError("workspace initialization requires a Graphflow v3 graph")
    entries: dict[str, Any] = {}
    slot = 0
    integration_refs: list[str] = []
    verifier_refs: list[str] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("kind") == "expand":
            continue
        link = node.get("executor") if isinstance(node.get("executor"), dict) else {}
        spec_path = workflow_dir / str(link.get("spec"))
        spec = load_json(spec_path, f"executor {node.get('id')}")
        contract = workspace_contract(spec)
        if contract["ref"] in entries:
            if contract["mode"] != "primary":
                raise ValueError(f"non-primary workspace ref {contract['ref']!r} is reused")
            continue
        entry = default_entry(str(node["id"]), contract, slot)
        entries[contract["ref"]] = entry
        if contract["mode"] == "integration":
            integration_refs.append(contract["ref"])
        elif contract["mode"] == "verifier":
            verifier_refs.append(contract["ref"])
        slot += 1
    source_ref = integration_refs[-1] if integration_refs else None
    for ref in verifier_refs:
        entries[ref]["source_ref"] = source_ref
    value = {
        "schema_version": 1,
        "workflow_id": graph.get("workflow_id"),
        "repo_root": None,
        "repo_common_dir": None,
        "entries": entries,
    }
    write_registry(workflow_dir, value)
    return value


def rebind(workflow_dir: Path, reassignments: dict[str, str] | None = None) -> dict[str, Any]:
    """Rebind a structurally revised graph while preserving compatible owned workspaces."""
    graph = load_json(workflow_dir / "graph.json", "graph")
    if not isinstance(graph, dict) or graph.get("version") != 3:
        raise ValueError("workspace rebind requires a Graphflow v3 graph")
    current = load_registry(workflow_dir, str(graph.get("workflow_id")))
    reassignments = reassignments or {}
    entries: dict[str, Any] = {}
    used_slots = {
        int(entry["allocations"]["slot"])
        for entry in current["entries"].values()
        if isinstance(entry, dict) and isinstance(entry.get("allocations"), dict) and isinstance(entry["allocations"].get("slot"), int)
    }
    next_slot = 0

    def allocate_slot() -> int:
        nonlocal next_slot
        while next_slot in used_slots:
            next_slot += 1
        value = next_slot
        used_slots.add(value)
        next_slot += 1
        return value

    integration_refs: list[str] = []
    verifier_refs: list[str] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("kind") == "expand":
            continue
        link = node.get("executor") if isinstance(node.get("executor"), dict) else {}
        spec = load_json(workflow_dir / str(link.get("spec")), f"executor {node.get('id')}")
        contract = workspace_contract(spec)
        if contract["ref"] in entries:
            if contract["mode"] != "primary":
                raise ValueError(f"non-primary workspace ref {contract['ref']!r} is reused")
            continue
        previous = current["entries"].get(contract["ref"])
        if isinstance(previous, dict) and previous.get("mode") == contract["mode"]:
            allowed_node = reassignments.get(str(previous.get("node_id")), str(previous.get("node_id")))
            if allowed_node != str(node.get("id")) and contract["mode"] != "primary":
                raise ValueError(f"workspace {contract['ref']!r} cannot be reassigned from {previous.get('node_id')} to {node.get('id')}")
            entry = json.loads(json.dumps(previous))
            entry["node_id"] = str(node["id"])
            entry["updated_at"] = now_utc()
        else:
            entry = default_entry(str(node["id"]), contract, allocate_slot())
        entries[contract["ref"]] = entry
        if contract["mode"] == "integration":
            integration_refs.append(contract["ref"])
        elif contract["mode"] == "verifier":
            verifier_refs.append(contract["ref"])
    source_ref = integration_refs[-1] if integration_refs else None
    for ref in verifier_refs:
        entries[ref]["source_ref"] = source_ref
    value = {
        "schema_version": 1,
        "workflow_id": graph.get("workflow_id"),
        "repo_root": current.get("repo_root"),
        "repo_common_dir": current.get("repo_common_dir"),
        "entries": entries,
    }
    validate_allocations(value)
    write_registry(workflow_dir, value)
    return value


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "workspace"


def registered_paths(repo_root: Path) -> set[Path]:
    output = git(repo_root, "worktree", "list", "--porcelain")
    return {Path(line.removeprefix("worktree ")).resolve() for line in output.splitlines() if line.startswith("worktree ")}


def dependency_order(graph: dict[str, Any], node_id: str) -> list[str]:
    nodes = node_map(graph)
    ordered: list[str] = []
    seen: set[str] = set()

    def visit(current: str) -> None:
        for dependency in nodes.get(current, {}).get("depends_on", []):
            if dependency in seen:
                continue
            visit(str(dependency))
            seen.add(str(dependency))
            ordered.append(str(dependency))

    visit(node_id)
    return ordered


def sync_dependencies(path: Path, graph: dict[str, Any], registry: dict[str, Any], node_id: str) -> None:
    consumer = next(
        (entry for entry in registry["entries"].values() if isinstance(entry, dict) and entry.get("node_id") == node_id),
        None,
    )
    records_integration = isinstance(consumer, dict) and consumer.get("mode") == "integration"
    entry_by_node = {
        str(entry.get("node_id")): entry
        for entry in registry["entries"].values()
        if isinstance(entry, dict) and isinstance(entry.get("checkpoint_sha"), str)
    }
    for dependency in dependency_order(graph, node_id):
        dependency_entry = entry_by_node.get(dependency)
        if dependency_entry is None:
            continue
        checkpoint_sha = dependency_entry["checkpoint_sha"]
        ancestor = subprocess.run(
            ["git", "-C", str(path), "merge-base", "--is-ancestor", checkpoint_sha, "HEAD"],
            capture_output=True, text=True, check=False,
        )
        if ancestor.returncode == 0:
            if records_integration:
                dependency_entry["status"] = "integrated"
                dependency_entry["updated_at"] = now_utc()
            continue
        try:
            git(path, "cherry-pick", checkpoint_sha, env=git_identity_env())
        except ValueError:
            git(path, "cherry-pick", "--abort", check=False)
            raise
        if records_integration:
            dependency_entry["status"] = "integrated"
            dependency_entry["updated_at"] = now_utc()


def provision_entry(workflow_dir: Path, repo_root: Path, ref: str) -> dict[str, Any]:
    graph = load_json(workflow_dir / "graph.json", "graph")
    registry = load_registry(workflow_dir, str(graph.get("workflow_id")))
    entry = registry["entries"].get(ref)
    if not isinstance(entry, dict):
        raise ValueError(f"unknown workspace ref {ref!r}")
    mode = entry["mode"]
    created = False
    if mode == "primary":
        path = repo_root.resolve()
        try:
            repo_root = repository_root(path)
            repo_common: Path | None = common_dir(repo_root)
            expected_branch = branch(repo_root)
            base: str | None = head(repo_root)
            path = repo_root
        except ValueError:
            repo_common = None
            expected_branch = "(non-git)"
            base = None
        registry["repo_root"] = str(path)
        registry["repo_common_dir"] = str(repo_common) if repo_common is not None else None
        entry.update(path=str(path), branch=expected_branch, base_sha=base, head_sha=base, status="ready", updated_at=now_utc())
    elif entry.get("status") in {"ready", "checkpointed", "accepted-no-change"} and isinstance(entry.get("path"), str):
        path = Path(entry["path"]).resolve()
    else:
        repo_root = repository_root(repo_root)
        registry["repo_root"] = str(repo_root)
        registry["repo_common_dir"] = str(common_dir(repo_root))
        source_sha = head(repo_root)
        if mode == "verifier":
            source = registry["entries"].get(entry.get("source_ref"))
            if not isinstance(source, dict) or not isinstance(source.get("checkpoint_sha"), str):
                raise ValueError(f"verifier workspace {ref!r} requires an accepted integration checkpoint")
            source_sha = source["checkpoint_sha"]
        node_slug = safe_slug(str(entry["node_id"]))
        workflow_slug = safe_slug(str(graph.get("workflow_id")))
        path = repo_root.parent / f"{repo_root.name}-graphflow-{workflow_slug}-{node_slug}"
        if path.exists() or path.resolve() in registered_paths(repo_root):
            raise ValueError(f"workspace target already exists or is registered: {path}")
        if mode == "verifier":
            git(repo_root, "worktree", "add", "--detach", str(path), source_sha)
            expected_branch = "(detached)"
        else:
            expected_branch = f"codex/{workflow_slug}-{node_slug}"
            if git(repo_root, "show-ref", "--verify", f"refs/heads/{expected_branch}", check=False).strip():
                raise ValueError(f"workspace branch already exists: {expected_branch}")
            git(repo_root, "worktree", "add", "-b", expected_branch, str(path), source_sha)
        created = True
        allocations = entry["allocations"]
        allocations["compose_project"] = f"graphflow-{workflow_slug}-{node_slug}"
        allocations["cache_dir"] = str(workflow_dir / "runtime" / "workspaces" / ref / "cache")
        allocations["log_dir"] = str(workflow_dir / "runtime" / "workspaces" / ref / "logs")
        entry.update(
            path=str(path.resolve()), branch=expected_branch, base_sha=source_sha, head_sha=source_sha,
            status="ready", updated_at=now_utc(),
        )
    if mode in {"worktree", "integration"}:
        try:
            sync_dependencies(path, graph, registry, str(entry["node_id"]))
        except ValueError:
            if created:
                git(repo_root, "worktree", "remove", "--force", str(path), check=False)
                if entry.get("branch") not in {None, "(detached)"}:
                    git(repo_root, "branch", "-D", str(entry["branch"]), check=False)
            raise
        entry["head_sha"] = head(path)
        entry["updated_at"] = now_utc()
    validate_entry(repo_root, registry, entry, require_clean=True)
    write_registry(workflow_dir, registry)
    return entry


def validate_entry(repo_root: Path, registry: dict[str, Any], entry: dict[str, Any], *, require_clean: bool) -> None:
    path_value = entry.get("path")
    if not isinstance(path_value, str) or not Path(path_value).is_dir():
        raise ValueError(f"workspace {entry.get('workspace_id')} path is missing")
    path = Path(path_value).resolve()
    if entry.get("mode") == "primary" and entry.get("branch") == "(non-git)":
        if path != repo_root.resolve():
            raise ValueError("non-Git primary workspace does not match repo-root")
        return
    if common_dir(path) != common_dir(repository_root(repo_root)):
        raise ValueError(f"workspace {entry.get('workspace_id')} belongs to another Git repository")
    actual_branch = branch(path)
    if actual_branch != entry.get("branch"):
        raise ValueError(f"workspace {entry.get('workspace_id')} branch drift: {actual_branch!r}")
    actual_head = head(path)
    if actual_head != entry.get("head_sha"):
        raise ValueError(f"workspace {entry.get('workspace_id')} HEAD drift")
    if require_clean and changed_files(path):
        raise ValueError(f"workspace {entry.get('workspace_id')} is dirty before dispatch")


def resolve(
    workflow_dir: Path,
    repo_root: Path,
    spec: dict[str, Any],
    node_id: str,
    *,
    provision: bool,
    require_clean: bool = True,
) -> tuple[Path, dict[str, Any]]:
    contract = workspace_contract(spec)
    registry = load_registry(workflow_dir)
    entry = registry["entries"].get(contract["ref"])
    if not isinstance(entry, dict):
        raise ValueError(f"workspace ref {contract['ref']!r} is not registered")
    if entry.get("mode") != "primary" and entry.get("node_id") != node_id:
        raise ValueError(f"workspace ref {contract['ref']!r} belongs to another node")
    if entry.get("status") == "unprovisioned":
        if not provision:
            raise ValueError(f"workspace {contract['ref']!r} is not provisioned")
        entry = provision_entry(workflow_dir, repo_root, contract["ref"])
        registry = load_registry(workflow_dir)
    validate_entry(repo_root, registry, entry, require_clean=require_clean)
    root = Path(entry["path"]).resolve()
    cwd = (root / contract["subdir"]).resolve()
    if not cwd.is_relative_to(root) or not cwd.is_dir():
        raise ValueError(f"workspace subdir is missing or escapes root: {contract['subdir']}")
    return cwd, entry


def snapshot(path: Path) -> dict[str, Any]:
    dirty = changed_files(path)
    if dirty:
        raise ValueError(f"workspace is dirty before dispatch: {', '.join(dirty)}")
    return {
        "head_sha": head(path), "branch": branch(path), "refs_digest": refs_digest(path),
        "git_metadata_digest": git_metadata_digest(path),
    }


def path_allowed(path: str, allowed: list[str]) -> bool:
    return any(path == owner or path.startswith(owner.rstrip("/") + "/") for owner in allowed)


def file_manifest(path: Path, files: list[str]) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    for relative in files:
        candidate = path / relative
        if candidate.is_symlink():
            digest = "sha256:" + hashlib.sha256(os.readlink(candidate).encode("utf-8")).hexdigest()
            kind = "symlink"
        elif candidate.is_file():
            digest = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            kind = "file"
        else:
            digest = "sha256:" + hashlib.sha256(b"missing").hexdigest()
            kind = "deleted"
        values.append({"path": relative, "kind": kind, "digest": digest})
    return values


def verify_scope(path: Path, node: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
    if (
        head(path) != before.get("head_sha")
        or branch(path) != before.get("branch")
        or refs_digest(path) != before.get("refs_digest")
        or git_metadata_digest(path) != before.get("git_metadata_digest")
    ):
        raise ValueError("worker changed Git HEAD, branch, shared refs, or protected Git metadata")
    changed = changed_files(path)
    scope = node.get("scope") if isinstance(node.get("scope"), dict) else {}
    allowed = scope.get("write") if isinstance(scope.get("write"), list) else []
    forbidden = scope.get("forbidden") if isinstance(scope.get("forbidden"), list) else []
    outside = [item for item in changed if not path_allowed(item, allowed)]
    denied = [item for item in changed if path_allowed(item, forbidden)]
    if outside or denied:
        detail = []
        if outside:
            detail.append("outside scope: " + ", ".join(outside))
        if denied:
            detail.append("forbidden: " + ", ".join(denied))
        raise ValueError("; ".join(detail))
    manifest = file_manifest(path, changed)
    changed_symlinks = [item["path"] for item in manifest if item["kind"] == "symlink"]
    if changed_symlinks:
        raise ValueError("changed symlinks require an explicit graph contract extension: " + ", ".join(changed_symlinks))
    return {"changed_files": changed, "patch_digest": json_digest(manifest), "manifest": manifest}


def checkpoint(workflow_dir: Path, ref: str, node_id: str, scope_report: dict[str, Any]) -> dict[str, Any]:
    registry = load_registry(workflow_dir)
    entry = registry["entries"].get(ref)
    if not isinstance(entry, dict) or entry.get("node_id") != node_id:
        raise ValueError("checkpoint workspace ownership mismatch")
    path = Path(str(entry.get("path"))).resolve()
    changed = scope_report.get("changed_files")
    if not isinstance(changed, list):
        raise ValueError("checkpoint requires a scope report")
    current_changed = changed_files(path)
    if not current_changed and entry.get("checkpoint_sha") == head(path) and entry.get("patch_digest") == scope_report.get("patch_digest"):
        return {
            "workspace_ref": ref, "checkpoint_sha": entry["checkpoint_sha"],
            "status": entry["status"], "patch_digest": entry["patch_digest"],
        }
    current_manifest = file_manifest(path, current_changed)
    current_digest = json_digest(current_manifest)
    if current_changed != changed or current_digest != scope_report.get("patch_digest"):
        raise ValueError("workspace changed after scope verification; refusing stale checkpoint")
    if changed:
        git(path, "add", "-A", "--", ".")
        git(path, "commit", "-m", f"graphflow({registry['workflow_id']}): checkpoint {node_id}", env=git_identity_env())
        status = "checkpointed"
    else:
        status = "accepted-no-change"
    checkpoint_sha = head(path)
    entry.update(
        head_sha=checkpoint_sha, checkpoint_sha=checkpoint_sha, patch_digest=scope_report.get("patch_digest"),
        status=status, updated_at=now_utc(),
    )
    write_registry(workflow_dir, registry)
    return {"workspace_ref": ref, "checkpoint_sha": checkpoint_sha, "status": status, "patch_digest": scope_report.get("patch_digest")}


def projection(workflow_dir: Path) -> list[dict[str, Any]]:
    registry = load_registry(workflow_dir)
    allowed = {"workspace_id", "node_id", "mode", "branch", "base_sha", "head_sha", "status", "allocations", "checkpoint_sha", "updated_at"}
    values: list[dict[str, Any]] = []
    for entry in registry["entries"].values():
        value = {key: entry[key] for key in allowed if key in entry}
        allocations = value.get("allocations")
        if isinstance(allocations, dict):
            value["allocations"] = {
                key: allocations[key]
                for key in ("slot", "port_offset", "database_suffix", "compose_project")
                if key in allocations
            }
        values.append(value)
    return values


def mark_status(workflow_dir: Path, ref: str, status: str) -> None:
    registry = load_registry(workflow_dir)
    entry = registry["entries"].get(ref)
    if not isinstance(entry, dict):
        raise ValueError(f"unknown workspace ref {ref!r}")
    entry["status"] = status
    entry["updated_at"] = now_utc()
    if isinstance(entry.get("path"), str) and entry.get("branch") != "(non-git)":
        entry["head_sha"] = head(Path(entry["path"]))
    write_registry(workflow_dir, registry)


def cleanup_entry(workflow_dir: Path, repo_root: Path, ref: str) -> dict[str, Any]:
    registry = load_registry(workflow_dir)
    entry = registry["entries"].get(ref)
    if not isinstance(entry, dict):
        raise ValueError(f"unknown workspace ref {ref!r}")
    if not entry.get("workflow_owned") or entry.get("mode") == "primary":
        raise ValueError("cleanup is limited to Graphflow-owned non-primary workspaces")
    if entry.get("status") not in {"integrated", "verified", "rejected-disposable"}:
        raise ValueError(f"workspace {ref!r} is not proven disposable")
    path_value = entry.get("path")
    if not isinstance(path_value, str):
        raise ValueError(f"workspace {ref!r} has no registered path")
    path = Path(path_value).resolve()
    if changed_files(path):
        raise ValueError(f"workspace {ref!r} is dirty; refusing cleanup")
    git(repository_root(repo_root), "worktree", "remove", str(path))
    entry.update(path=None, status="cleaned", updated_at=now_utc())
    write_registry(workflow_dir, registry)
    return {"workspace_ref": ref, "status": "cleaned", "path": str(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("workflow_dir", type=Path)
    provision = commands.add_parser("provision")
    provision.add_argument("workflow_dir", type=Path)
    provision.add_argument("--repo-root", type=Path, required=True)
    provision.add_argument("--workspace-ref", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("workflow_dir", type=Path)
    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("workflow_dir", type=Path)
    cleanup.add_argument("--repo-root", type=Path, required=True)
    cleanup.add_argument("--workspace-ref", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            result: Any = initialize(args.workflow_dir.resolve())
        elif args.command == "provision":
            result = provision_entry(args.workflow_dir.resolve(), args.repo_root.resolve(), args.workspace_ref)
        elif args.command == "inspect":
            result = projection(args.workflow_dir.resolve())
        else:
            result = cleanup_entry(args.workflow_dir.resolve(), args.repo_root.resolve(), args.workspace_ref)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
