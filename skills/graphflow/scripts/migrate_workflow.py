#!/usr/bin/env python3
"""Copy a Graphflow v1/v2 workflow into the current v3 contract without changing the source."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from executor_common import atomic_json, load_json, sha256
import workspace_manager
import delivery_broker
import checkout_guard
import decomposition_broker


ROOT = Path(__file__).resolve().parents[1]
CURRENT_RESULT_SCHEMA = ROOT / "assets" / "workflow-template" / "nodes" / "node-result.schema.json"
CURRENT_REVIEW = ROOT / "assets" / "workflow-template" / "question-review.json"


def _migrate(source: Path, target: Path) -> dict[str, Any]:
    if source.resolve() == target.resolve():
        raise ValueError("target must differ from source; migration never edits a v1 workflow in place")
    if target.exists():
        raise ValueError("target already exists")
    graph = load_json(source / "graph.json", "source graph")
    if not isinstance(graph, dict) or graph.get("version") not in {1, 2}:
        raise ValueError("source must be a Graphflow v1 or v2 workflow")
    source_version = int(graph["version"])
    if not isinstance(graph.get("workflow_id"), str) or not isinstance(graph.get("nodes"), list):
        raise ValueError("source graph is missing workflow identity or nodes")
    shutil.copytree(source, target)
    target_graph_path = target / "graph.json"
    target_graph = load_json(target_graph_path, "copied graph")
    target_graph["version"] = 3
    target_graph.setdefault("lifecycle", {})["status"] = "draft"
    old_gate = target_graph.get("question_gate") if isinstance(target_graph.get("question_gate"), dict) else {}
    unresolved = old_gate.get("unresolved_pivotal") if isinstance(old_gate.get("unresolved_pivotal"), list) else []
    target_graph["question_gate"] = {
        "methods": ["Rumsfeld Matrix", "Value of Information", "Reversibility"],
        "status": "open" if unresolved else "clear",
        "unresolved_pivotal": unresolved,
        "review": {
            "status": "required",
            "artifact": "question-review.json",
            "digest": None,
            "graph_digest": None,
            "reviewer_id": None,
        },
    }
    integrity = target_graph.get("integrity") if isinstance(target_graph.get("integrity"), dict) else {}
    integrity.update(status="proposed", plan_digest=None, runner_digest=None)
    target_graph["integrity"] = integrity
    target_graph["execution_trust"] = {
        "schema_version": 1,
        "policy": "risk-adaptive-workspace-v1",
        "workspace_registry": "runtime/workspaces.json",
        "progress_dir": "runtime/progress",
        "required_phases": {
            "low": ["scope_accepted", "evidence_passed"],
            "medium": ["scope_accepted", "evidence_passed", "independently_verified"],
            "high": ["scope_accepted", "evidence_passed", "independently_verified", "externally_verified"],
        },
    }

    result_schema = target / "nodes" / "node-result.schema.json"
    result_schema.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CURRENT_RESULT_SCHEMA, result_schema)
    for node in target_graph["nodes"]:
        if not isinstance(node, dict) or node.get("kind") == "expand":
            continue
        link = node.get("executor")
        if not isinstance(link, dict) or not isinstance(link.get("spec"), str):
            raise ValueError(f"node {node.get('id')} has no migratable executor link")
        spec_path = target / link["spec"]
        spec = load_json(spec_path, f"executor {node.get('id')}")
        if not isinstance(spec, dict) or not isinstance(spec.get("resources"), list):
            raise ValueError(f"node {node.get('id')} has no migratable executor resources")
        replaced = False
        for resource in spec["resources"]:
            if isinstance(resource, dict) and resource.get("path") == "nodes/node-result.schema.json":
                resource["digest"] = sha256(result_schema)
                replaced = True
        if not replaced:
            raise ValueError(f"node {node.get('id')} does not lock the standard result schema")
        old_cwd = spec.pop("cwd", ".")
        mode = "verifier" if node.get("kind") == "verify" else "integration" if node.get("isolation") == "integration" else "worktree" if node.get("isolation") == "worktree" else "primary"
        workspace_ref = "primary" if mode == "primary" else f"workspace-{str(node.get('id')).lower()}"
        spec["schema_version"] = 2
        spec["workspace"] = {"mode": mode, "ref": workspace_ref, "subdir": old_cwd}
        atomic_json(spec_path, spec)
        link["digest"] = sha256(spec_path)

    runtime_path = target / "runtime.json"
    runtime = load_json(runtime_path, "runtime")
    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object")
    runtime.setdefault("authority_grants", {})
    runtime["delivery"] = delivery_broker.default_config()
    runtime["checkout_guard"] = checkout_guard.default_config()
    runtime["decomposition"] = decomposition_broker.default_config()
    scheduler = runtime.setdefault("scheduler", {})
    if isinstance(scheduler, dict):
        scheduler.update(status="idle", pid=None, blocker="Migrated to v3; workspace provisioning, independent question review, and relocking required.")
    atomic_json(runtime_path, runtime)

    plan_path = target / "integrity" / "verification-plan.json"
    plan = load_json(plan_path, "verification plan")
    external = plan.get("external_gate") if isinstance(plan, dict) else None
    if isinstance(external, dict):
        external.setdefault("provenance", None)
        atomic_json(plan_path, plan)

    review = load_json(CURRENT_REVIEW, "review template")
    review["workflow_id"] = target_graph["workflow_id"]
    review["graph_digest"] = None
    review["reviewer"]["agent_id"] = "replace-with-independent-reviewer"
    review["reviewer"]["model_id"] = None
    review["challenges"] = []
    review["findings"] = []
    review["status"] = "passed"
    review["reviewed_at"] = None
    atomic_json(target / "question-review.json", review)

    lock_path = target / "integrity" / "lock.json"
    if lock_path.is_file():
        lock = load_json(lock_path, "integrity lock")
        if isinstance(lock, dict):
            lock.update(status="template", plan_digest=None, runner_digest=None, contract_digest=None, locked_at=None)
            atomic_json(lock_path, lock)
    atomic_json(target_graph_path, target_graph)
    workspace_manager.initialize(target)

    memory_state = target / "memory" / "state.json"
    memory_events = target / "memory" / "events.jsonl"
    memory_rebound = False
    if memory_state.is_file() and memory_events.is_file() and memory_events.stat().st_size:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "memory_state.py"), "bind-graph", str(target)],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode:
            raise ValueError(f"migrated memory rebind failed: {(completed.stdout + completed.stderr).strip()}")
        memory_rebound = True

    report = {
        "schema_version": 1,
        "workflow_id": target_graph["workflow_id"],
        "source_version": source_version,
        "source": str(source.resolve()),
        "source_graph_digest": sha256(source / "graph.json"),
        "target": str(target.resolve()),
        "target_version": 3,
        "memory_rebound": memory_rebound,
        "required_next": [
            "provision and validate registered workspaces",
            "initialize the primary checkout baseline before any dispatch",
            "replace question-review.json with a fresh independent review",
            "lock the question gate",
            "relock integrity and executors after any semantic change",
            "validate executable before cutover",
        ],
    }
    atomic_json(target / "migration-to-v3.json", report)
    return report


def migrate(source: Path, target: Path) -> dict[str, Any]:
    """Migrate into a new directory and remove only a newly-created partial target on failure."""
    target_existed = target.exists()
    try:
        return _migrate(source, target)
    except Exception:
        if not target_existed and target.exists():
            shutil.rmtree(target)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = migrate(args.source.resolve(), args.output.resolve())
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
