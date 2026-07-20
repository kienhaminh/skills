#!/usr/bin/env python3
"""Atomically inspect and transition workflow graph node state."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


NON_EXPANSION_STATUSES = {
    "pending",
    "active",
    "waiting_user",
    "waiting_approval",
    "waiting_external",
    "stale",
    "blocked",
    "complete",
    "failed",
}
EXPANSION_STATUSES = (NON_EXPANSION_STATUSES - {"complete"}) | {"expanded"}
DEPENDENCY_GATED = {"active", "waiting_user", "waiting_approval", "waiting_external", "stale", "complete"}
TRANSITIONS = {
    "pending": {"active", "waiting_approval", "blocked", "failed"},
    "active": {"active", "waiting_user", "waiting_approval", "waiting_external", "stale", "blocked", "complete", "expanded", "failed"},
    "waiting_user": {"active", "blocked", "failed"},
    "waiting_approval": {"active", "blocked", "failed"},
    "waiting_external": {"active", "blocked", "failed"},
    "stale": {"pending", "active", "blocked", "failed"},
    "blocked": {"pending", "active", "failed"},
    "failed": {"pending", "active", "blocked"},
    "complete": {"complete"},
    "expanded": {"expanded"},
}
WORKFLOW_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_graph(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read graph: {error}") from error
    if not isinstance(value, dict) or not isinstance(value.get("nodes"), list):
        raise ValueError("graph root must contain a nodes list")
    return value


def resolve_workflow(args: argparse.Namespace) -> dict[str, Any]:
    if not WORKFLOW_ID_RE.fullmatch(args.workflow_id):
        raise ValueError("workflow_id must be kebab-case")
    root = Path(args.root).resolve()
    candidates = [
        root / args.workflow_id / "graph.json",
        root / "completed" / args.workflow_id / "graph.json",
    ]
    matches = [path for path in candidates if path.is_file()]
    if not matches:
        raise ValueError(f"workflow {args.workflow_id} not found under {root}")
    if len(matches) > 1:
        raise ValueError(f"workflow {args.workflow_id} exists in both active and completed locations")
    graph = read_graph(matches[0])
    if graph.get("workflow_id") != args.workflow_id:
        raise ValueError(f"resolved graph declares workflow_id {graph.get('workflow_id')!r}")
    lifecycle = graph.get("lifecycle") if isinstance(graph.get("lifecycle"), dict) else {}
    return {
        "workflow_id": args.workflow_id,
        "graph": str(matches[0]),
        "location": "completed" if "completed" in matches[0].relative_to(root).parts else "active",
        "status": lifecycle.get("status", "unknown"),
    }


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node.get("id"): node for node in graph["nodes"] if isinstance(node, dict) and isinstance(node.get("id"), str)}


def ready_ids(graph: dict[str, Any]) -> list[str]:
    nodes = node_map(graph)
    ready: list[str] = []
    for node_id, node in nodes.items():
        if node.get("kind") == "expand" or node.get("status") != "pending":
            continue
        dependencies = node.get("depends_on") if isinstance(node.get("depends_on"), list) else []
        if all(nodes.get(dependency, {}).get("status") == "complete" for dependency in dependencies):
            ready.append(node_id)
    return sorted(ready)


def parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def transition(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.graph).resolve()
    graph = read_graph(path)
    nodes = node_map(graph)
    node = nodes.get(args.node)
    if node is None:
        raise ValueError(f"unknown node {args.node}")
    allowed = EXPANSION_STATUSES if node.get("kind") == "expand" else NON_EXPANSION_STATUSES
    if args.status not in allowed:
        raise ValueError(f"status {args.status} is invalid for node kind {node.get('kind')}")
    current_status = node.get("status")
    if args.status not in TRANSITIONS.get(str(current_status), set()):
        raise ValueError(f"invalid transition for {args.node}: {current_status} -> {args.status}")
    dependencies = node.get("depends_on") if isinstance(node.get("depends_on"), list) else []
    incomplete = [dependency for dependency in dependencies if nodes.get(dependency, {}).get("status") != "complete"]
    if args.status in DEPENDENCY_GATED and incomplete:
        raise ValueError(f"cannot mark {args.node} {args.status}; incomplete dependencies: {', '.join(incomplete)}")

    retry = node.setdefault("retry", {"attempts": 0, "max_attempts": 2, "last_failure_class": None})
    increment_attempt = args.increment_attempt or (args.status == "active" and current_status in {"pending", "stale", "blocked", "failed"})
    if increment_attempt:
        attempts = int(retry.get("attempts", 0)) + 1
        maximum = int(retry.get("max_attempts", 2))
        if attempts > maximum:
            raise ValueError(f"node {args.node} exhausted {maximum} attempts")
        retry["attempts"] = attempts
    if args.failure_class is not None:
        retry["last_failure_class"] = args.failure_class

    timestamp = now_utc()
    runtime = node.setdefault("runtime", {})
    node["status"] = args.status
    runtime["updated_at"] = timestamp
    runtime["heartbeat_at"] = timestamp
    if args.agent is not None:
        runtime["agent"] = args.agent
    if args.model is not None:
        runtime["model"] = args.model
    if args.reasoning_effort is not None:
        runtime["reasoning_effort"] = args.reasoning_effort
    if args.summary is not None:
        runtime["summary"] = args.summary
    if args.blocker is not None:
        runtime["blocker"] = args.blocker
    if args.tokens_used is not None:
        runtime["tokens_used"] = args.tokens_used
    if args.status == "active" and not runtime.get("started_at"):
        runtime["started_at"] = timestamp
    if args.status in {"complete", "expanded"}:
        runtime["completed_at"] = timestamp
        runtime["blocker"] = None
    elif args.status not in {"blocked", "waiting_user", "waiting_approval", "waiting_external", "stale", "failed"}:
        runtime["blocker"] = None
    atomic_write(path, graph)
    return {"node": args.node, "status": args.status, "ready": ready_ids(graph), "updated_at": timestamp}


def reconcile(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.graph).resolve()
    graph = read_graph(path)
    live_agents = set(args.live_agent or [])
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=args.stale_after_minutes)
    changed: list[str] = []
    timestamp = now_utc()
    for node in graph["nodes"]:
        if not isinstance(node, dict) or node.get("status") != "active":
            continue
        runtime = node.get("runtime") if isinstance(node.get("runtime"), dict) else {}
        agent = runtime.get("agent")
        heartbeat = parse_time(runtime.get("heartbeat_at") or runtime.get("updated_at") or runtime.get("started_at"))
        missing_agent = bool(args.assume_no_live_agents or live_agents) and (not agent or agent not in live_agents)
        expired = heartbeat is None or heartbeat < cutoff
        if not missing_agent and not expired:
            continue
        node["status"] = "stale"
        runtime["updated_at"] = timestamp
        runtime["heartbeat_at"] = timestamp
        runtime["blocker"] = "Worker lost or heartbeat expired; inspect owned worktree and artifacts before retry."
        runtime["summary"] = "Reconciliation marked this node stale."
        node["runtime"] = runtime
        changed.append(str(node.get("id")))
    if changed:
        atomic_write(path, graph)
    return {"stale_nodes": changed, "ready": ready_ids(graph), "updated_at": timestamp}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    ready_parser = subparsers.add_parser("ready", help="Print ready node IDs")
    ready_parser.add_argument("graph")

    resolve_parser = subparsers.add_parser("resolve", help="Resolve one workflow ID to its exact graph")
    resolve_parser.add_argument("root")
    resolve_parser.add_argument("--workflow-id", required=True)

    transition_parser = subparsers.add_parser("transition", help="Update one node atomically")
    transition_parser.add_argument("graph")
    transition_parser.add_argument("--node", required=True)
    transition_parser.add_argument("--status", required=True)
    transition_parser.add_argument("--agent")
    transition_parser.add_argument("--model")
    transition_parser.add_argument("--reasoning-effort")
    transition_parser.add_argument("--summary")
    transition_parser.add_argument("--blocker")
    transition_parser.add_argument("--tokens-used", type=int)
    transition_parser.add_argument("--failure-class", choices=("contract", "context", "reasoning", "environment", "authority", "external"))
    transition_parser.add_argument("--increment-attempt", action="store_true")

    reconcile_parser = subparsers.add_parser("reconcile", help="Mark lost or expired active workers stale")
    reconcile_parser.add_argument("graph")
    reconcile_parser.add_argument("--live-agent", action="append")
    reconcile_parser.add_argument("--assume-no-live-agents", action="store_true")
    reconcile_parser.add_argument("--stale-after-minutes", type=int, default=30)

    args = parser.parse_args()
    try:
        if args.command == "resolve":
            result = resolve_workflow(args)
        elif args.command == "ready":
            result = {"ready": ready_ids(read_graph(Path(args.graph).resolve()))}
        elif args.command == "transition":
            result = transition(args)
        else:
            if args.stale_after_minutes < 0:
                raise ValueError("--stale-after-minutes must be non-negative")
            result = reconcile(args)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
