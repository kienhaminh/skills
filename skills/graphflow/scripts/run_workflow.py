#!/usr/bin/env python3
"""Run or resume a persistent Graphflow DAG without depending on Goal."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import re
from pathlib import Path
from typing import Any

import workflow_state
import progress_state
import workspace_manager
import delivery_broker
import checkout_guard
import decomposition_broker
import evidence_runner
from executor_common import (
    AUTHORITY_CAPABILITIES,
    DIGEST_RE,
    QUESTION_IMPACTS,
    SEMANTIC_QUESTION_IMPACTS,
    append_event,
    atomic_json,
    canonical_graph_digest,
    load_executor,
    load_json,
    now_utc,
    validate_result,
)


SCRIPT_ROOT = Path(__file__).resolve().parent
NODE_RUNNER = SCRIPT_ROOT / "node_runner.py"
VALIDATOR = SCRIPT_ROOT / "validate_graph.py"
MEMORY = SCRIPT_ROOT / "memory_state.py"
EVIDENCE = SCRIPT_ROOT / "evidence_runner.py"
QUESTION_GATE = SCRIPT_ROOT / "question_gate.py"


def run_checked(argv: list[str]) -> tuple[bool, str]:
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    return completed.returncode == 0, (completed.stdout + completed.stderr).strip()


def pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class Lease:
    def __init__(self, workflow_dir: Path, recover: bool, stale_seconds: int):
        self.path = workflow_dir / "runtime" / "lease.json"
        self.token = secrets.token_hex(16)
        self.recover = recover
        self.stale_seconds = stale_seconds

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            current = load_json(self.path, "workflow lease")
            age = time.time() - self.path.stat().st_mtime
            stale = isinstance(current, dict) and not pid_alive(current.get("pid")) and age >= self.stale_seconds
            if not (self.recover and stale):
                raise ValueError("workflow lease is already held; use --recover-stale-lease only after checking the recorded owner")
            self.path.unlink()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(self.path, flags, 0o600)
        value = {"schema_version": 1, "token": self.token, "pid": os.getpid(), "acquired_at": now_utc(), "heartbeat_at": now_utc()}
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def heartbeat(self) -> None:
        current = load_json(self.path, "workflow lease")
        if not isinstance(current, dict) or current.get("token") != self.token:
            raise ValueError("workflow lease ownership changed")
        current["heartbeat_at"] = now_utc()
        atomic_json(self.path, current)

    def release(self) -> None:
        if not self.path.exists():
            return
        current = load_json(self.path, "workflow lease")
        if isinstance(current, dict) and current.get("token") == self.token:
            self.path.unlink()


def save_runtime(workflow_dir: Path, graph: dict[str, Any], status: str, blocker: str | None = None) -> None:
    path = workflow_dir / "runtime.json"
    existing = load_json(path, "runtime") if path.is_file() else {}
    if not isinstance(existing, dict):
        existing = {}
    existing.update(
        schema_version=1,
        workflow_id=graph.get("workflow_id"),
        scheduler={"status": status, "pid": os.getpid() if status == "active" else None, "updated_at": now_utc(), "blocker": blocker},
    )
    existing.setdefault("goal_adapter", None)
    existing.setdefault("delivery", delivery_broker.default_config())
    existing.setdefault("checkout_guard", checkout_guard.default_config())
    existing.setdefault("decomposition", decomposition_broker.default_config())
    atomic_json(path, existing)


def checkout_gate(workflow_dir: Path, repo_root: Path) -> tuple[str, str | None]:
    snapshot = checkout_guard.advance(workflow_dir, repo_root)
    status = str(snapshot.get("status"))
    if status == "clear":
        return "clear", None
    runtime = load_json(workflow_dir / "runtime.json", "runtime")
    config = runtime.get("checkout_guard") if isinstance(runtime, dict) and isinstance(runtime.get("checkout_guard"), dict) else {}
    blocker = config.get("failure") if isinstance(config.get("failure"), str) else "Primary checkout drift requires digest-bound confirmation."
    return status, blocker


def stop_if_checkout_drifted(
    workflow_dir: Path, repo_root: Path, graph: dict[str, Any], events_path: Path, *, once: bool = False,
) -> int | None:
    guard_status, blocker = checkout_gate(workflow_dir, repo_root)
    if guard_status == "clear":
        return None
    scheduler_status = "blocked" if guard_status == "blocked" else "waiting"
    save_runtime(workflow_dir, graph, scheduler_status, blocker)
    event = {"type": "runner_stopped", "at": now_utc(), "status": scheduler_status, "blocker": blocker}
    if once:
        event["once"] = True
    append_event(events_path, event)
    print(json.dumps({"workflow_id": graph.get("workflow_id"), "status": scheduler_status, "blocker": blocker}, indent=2))
    return 1 if scheduler_status == "blocked" else 0


def set_lifecycle(graph_path: Path, status: str) -> dict[str, Any]:
    graph = workflow_state.read_graph(graph_path)
    graph.setdefault("lifecycle", {})["status"] = status
    workflow_state.atomic_write(graph_path, graph)
    return graph


def verify_executors(workflow_dir: Path, graph: dict[str, Any]) -> None:
    registry = workspace_manager.load_registry(workflow_dir, str(graph.get("workflow_id")))
    for node in graph.get("nodes", []):
        if isinstance(node, dict) and node.get("kind") != "expand":
            _, _, spec, _ = load_executor(workflow_dir, str(node.get("id")))
            contract = workspace_manager.workspace_contract(spec)
            entry = registry["entries"].get(contract["ref"])
            expected_mode = "verifier" if node.get("kind") == "verify" else "integration" if node.get("isolation") == "integration" else "worktree" if node.get("isolation") == "worktree" else "primary"
            if not isinstance(entry, dict) or entry.get("mode") != expected_mode or contract["mode"] != expected_mode:
                raise ValueError(f"node {node.get('id')} workspace registry/mode does not match isolation contract")


def granted_capabilities(runtime: dict[str, Any], node_id: str) -> set[str]:
    global_authority = runtime.get("authority") if isinstance(runtime.get("authority"), dict) else {}
    grants = runtime.get("authority_grants") if isinstance(runtime.get("authority_grants"), dict) else {}
    node_grant = grants.get(node_id) if isinstance(grants.get(node_id), dict) else {}
    scoped = set(node_grant.get("capabilities", [])) if isinstance(node_grant.get("capabilities"), list) else set()
    return scoped | {capability for capability, granted in global_authority.items() if granted is True}


def authority_risks(capabilities: list[str]) -> list[str]:
    risk_by_capability = {
        "local_write": "May modify files inside the declared node scope.",
        "commit": "Creates durable local Git history.",
        "push": "Mutates a configured remote branch.",
        "pull_request": "Creates or updates a remote pull request.",
        "merge": "Changes the remote integration branch and is not implied by pull-request authority.",
        "deploy": "Changes a deployed environment and may affect users.",
        "destructive": "May remove or irreversibly transform in-scope state.",
        "network": "Contacts external services under the executor contract.",
        "credentials": "Uses configured credentials without persisting their values.",
    }
    return [risk_by_capability[value] for value in capabilities]


def ensure_authority_requests(workflow_dir: Path, graph_path: Path) -> list[str]:
    graph = workflow_state.read_graph(graph_path)
    runtime = load_json(workflow_dir / "runtime.json", "runtime authority")
    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object")
    created: list[str] = []
    for node_id in workflow_state.ready_ids(graph):
        if request_path_for(workflow_dir, node_id) is not None:
            continue
        _, _, spec, _ = load_executor(workflow_dir, node_id)
        missing = sorted(set(spec.get("requires_authority", [])) - granted_capabilities(runtime, node_id))
        if not missing:
            continue
        triage = {
            "blocking_scope": "branch",
            "impacts": ["authority"],
            "affected_nodes": [node_id],
            "no_safe_default_reason": "Graphflow never infers capabilities that mutate files, remotes, deployments, credentials, or external systems.",
            "resolution_mode": "resume",
            "request_graph_digest": canonical_graph_digest(graph),
            "authority_capabilities": missing,
        }
        question = f"Grant node {node_id} these declared capabilities: {', '.join(missing)}?"
        alternatives = ["Grant only to this workflow node", "Reject and keep the branch blocked"]
        risks = authority_risks(missing)
        surface = json.dumps(
            {"question": question, "alternatives": alternatives, "risks": risks, "triage": triage},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        request_id = f"authority-{node_id.lower()}-{hashlib.sha256(surface).hexdigest()[:12]}"
        result = {
            "request": {
                "request_id": request_id,
                "digest": "sha256:" + hashlib.sha256(surface).hexdigest(),
                "question": question,
                "alternatives": alternatives,
                "risks": risks,
                "triage": triage,
            }
        }
        request = store_request(workflow_dir, graph, node_id, result)
        workflow_state.transition(arg_namespace(graph_path, node_id, "waiting_approval", summary="Declared authority requires user confirmation.", blocker=f"Confirmation required: {request.name}"))
        created.append(node_id)
        graph = workflow_state.read_graph(graph_path)
    return created


def revoke_node_grant(workflow_dir: Path, node_id: str) -> None:
    runtime_path = workflow_dir / "runtime.json"
    runtime = load_json(runtime_path, "runtime authority")
    grants = runtime.get("authority_grants") if isinstance(runtime, dict) else None
    if isinstance(grants, dict) and node_id in grants:
        del grants[node_id]
        atomic_json(runtime_path, runtime)


def reconcile_lost_active(graph_path: Path) -> list[str]:
    graph = workflow_state.read_graph(graph_path)
    recovered: list[str] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("status") != "active":
            continue
        result = graph_path.parent / "runtime" / "results" / f"{node.get('id')}.json"
        if result.is_file():
            continue
        workflow_state.transition(arg_namespace(graph_path, str(node["id"]), "stale", summary="Recovered an interrupted executor."))
        workflow_state.transition(arg_namespace(graph_path, str(node["id"]), "pending", summary="Queued idempotent retry after interruption."))
        recovered.append(str(node["id"]))
    return recovered


def arg_namespace(graph_path: Path, node: str, status: str, **values: Any) -> argparse.Namespace:
    defaults = {
        "graph": str(graph_path), "node": node, "status": status, "agent": None, "model": None,
        "reasoning_effort": None, "summary": None, "blocker": None, "tokens_used": None,
        "failure_class": None, "increment_attempt": False,
    }
    defaults.update(values)
    return argparse.Namespace(**defaults)


def request_path_for(workflow_dir: Path, node_id: str) -> Path | None:
    directory = workflow_dir / "runtime" / "requests"
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*.json")):
        value = load_json(path, "confirmation request")
        if isinstance(value, dict) and value.get("node_id") == node_id and value.get("status") in {"pending", "approved", "rejected"}:
            return path
    return None


def has_pending_workflow_request(workflow_dir: Path) -> bool:
    directory = workflow_dir / "runtime" / "requests"
    if not directory.is_dir():
        return False
    for path in directory.glob("*.json"):
        value = load_json(path, "confirmation request")
        if not isinstance(value, dict):
            continue
        triage = value.get("triage")
        if value.get("status") == "pending" and isinstance(triage, dict) and triage.get("blocking_scope") == "workflow":
            return True
    return False


def workflow_scoped_resumes(resumed: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    selected: list[tuple[str, Path]] = []
    for item in resumed:
        value = load_json(item[1], "confirmation request")
        triage = value.get("triage") if isinstance(value, dict) else None
        if isinstance(triage, dict) and triage.get("blocking_scope") == "workflow":
            selected.append(item)
    return selected


def rebase_gates_pass(workflow_dir: Path, repo_root: Path, graph_path: Path) -> tuple[bool, str]:
    checks = [
        [sys.executable, str(VALIDATOR), str(graph_path), "--phase", "executable"],
        [sys.executable, str(MEMORY), "--repo-root", str(repo_root), "validate", str(workflow_dir), "--phase", "active"],
        [sys.executable, str(EVIDENCE), "validate", str(workflow_dir), "--phase", "active", "--repo-root", str(repo_root)],
    ]
    failures = [output for ok, output in (run_checked(argv) for argv in checks) if not ok]
    return not failures, " | ".join(failures)


def approved_resumes(workflow_dir: Path, repo_root: Path, graph_path: Path) -> list[tuple[str, Path]]:
    graph = workflow_state.read_graph(graph_path)
    current_digest = canonical_graph_digest(graph)
    ready: list[tuple[str, Path]] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("status") not in {"waiting_user", "waiting_approval"}:
            continue
        path = request_path_for(workflow_dir, str(node["id"]))
        if path is None:
            continue
        request = load_json(path, "confirmation request")
        if request.get("status") == "rejected":
            workflow_state.transition(arg_namespace(graph_path, str(node["id"]), "blocked", blocker="User rejected the digest-bound request."))
            revoke_node_grant(workflow_dir, str(node["id"]))
        elif request.get("status") == "approved":
            triage = request.get("triage") if isinstance(request.get("triage"), dict) else {}
            resolution_mode = triage.get("resolution_mode")
            requested_digest = triage.get("request_graph_digest")
            if resolution_mode == "resume" and requested_digest != current_digest:
                request["status"] = "invalidated"
                request["invalidated_reason"] = "semantic graph changed after approval"
                atomic_json(path, request)
                workflow_state.transition(arg_namespace(graph_path, str(node["id"]), "blocked", blocker="Confirmation invalidated because the graph changed; issue a new request."))
                revoke_node_grant(workflow_dir, str(node["id"]))
                continue
            if resolution_mode == "rebase":
                if requested_digest == current_digest:
                    continue
                valid, _ = rebase_gates_pass(workflow_dir, repo_root, graph_path)
                if not valid:
                    continue
            ready.append((str(node["id"]), path))
    return ready


def execute_node(workflow_dir: Path, repo_root: Path, node_id: str, codex_bin: str, confirmation: Path | None) -> tuple[str, int, str]:
    argv = [
        sys.executable, str(NODE_RUNNER), str(workflow_dir), "--node", node_id,
        "--repo-root", str(repo_root), "--codex-bin", codex_bin,
    ]
    if confirmation is not None:
        argv.extend(["--confirmation-file", str(confirmation)])
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    return node_id, completed.returncode, (completed.stdout + completed.stderr).strip()


def select_safe_frontier(
    workflow_dir: Path, repo_root: Path, graph: dict[str, Any], candidates: list[tuple[str, Path | None]], limit: int,
) -> list[tuple[str, Path | None]]:
    nodes = workflow_state.node_map(graph)
    selected: list[tuple[str, Path | None]] = []
    modifying_roots: set[Path] = set()
    for node_id, confirmation in candidates:
        if len(selected) >= limit:
            break
        node = nodes[node_id]
        _, _, spec, _ = load_executor(workflow_dir, node_id)
        _, workspace = workspace_manager.resolve(workflow_dir, repo_root, spec, node_id, provision=True)
        root = Path(str(workspace["path"])).resolve()
        scope = node.get("scope") if isinstance(node.get("scope"), dict) else {}
        modifies = bool(scope.get("write"))
        if modifies and root in modifying_roots:
            continue
        selected.append((node_id, confirmation))
        if modifies:
            modifying_roots.add(root)
    return selected


def dependency_descendants(graph: dict[str, Any], node_id: str) -> set[str]:
    reverse: dict[str, set[str]] = {}
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            continue
        for dependency in node.get("depends_on", []):
            if isinstance(dependency, str):
                reverse.setdefault(dependency, set()).add(node["id"])
    found: set[str] = set()
    stack = list(reverse.get(node_id, set()))
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        stack.extend(reverse.get(current, set()))
    return found


def store_request(workflow_dir: Path, graph: dict[str, Any], node_id: str, result: dict[str, Any]) -> Path:
    request = result.get("request")
    if not isinstance(request, dict):
        raise ValueError("waiting result has no request object")
    request_id = request.get("request_id")
    digest = request.get("digest")
    question = request.get("question")
    alternatives = request.get("alternatives")
    risks = request.get("risks")
    triage = request.get("triage")
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", request_id):
        raise ValueError("request_id must be a stable path-safe identifier")
    if not isinstance(question, str) or not question or not isinstance(alternatives, list) or not isinstance(risks, list):
        raise ValueError("request requires a question plus alternatives and risks lists")
    if any(not isinstance(value, str) or not value for value in alternatives + risks):
        raise ValueError("request alternatives and risks must contain non-empty strings")
    triage_fields = {
        "blocking_scope", "impacts", "affected_nodes", "no_safe_default_reason",
        "resolution_mode", "request_graph_digest", "authority_capabilities",
    }
    if not isinstance(triage, dict) or set(triage) != triage_fields:
        raise ValueError(f"request triage must contain exactly {sorted(triage_fields)!r}")
    if triage.get("blocking_scope") not in {"branch", "workflow"}:
        raise ValueError("request triage blocking_scope must be branch or workflow")
    impacts = triage.get("impacts")
    if not isinstance(impacts, list) or not impacts or any(value not in QUESTION_IMPACTS for value in impacts) or len(impacts) != len(set(impacts)):
        raise ValueError("request triage impacts must be a unique non-empty controlled list")
    affected = triage.get("affected_nodes")
    known_nodes = set(workflow_state.node_map(graph))
    if not isinstance(affected, list) or not affected or any(value not in known_nodes for value in affected) or len(affected) != len(set(affected)):
        raise ValueError("request triage affected_nodes must contain unique existing node IDs")
    if node_id not in affected:
        raise ValueError("request triage affected_nodes must include the requesting node")
    if triage["blocking_scope"] == "branch" and not set(affected).issubset({node_id, *dependency_descendants(graph, node_id)}):
        raise ValueError("branch request may affect only the requesting node and its descendants")
    if not isinstance(triage.get("no_safe_default_reason"), str) or not triage["no_safe_default_reason"].strip():
        raise ValueError("request triage must explain why no safe reversible default exists")
    resolution_mode = triage.get("resolution_mode")
    if resolution_mode not in {"resume", "rebase"}:
        raise ValueError("request triage resolution_mode must be resume or rebase")
    if SEMANTIC_QUESTION_IMPACTS.intersection(impacts) and resolution_mode != "rebase":
        raise ValueError("semantic impacts require request triage resolution_mode rebase")
    request_graph_digest = triage.get("request_graph_digest")
    current_graph_digest = canonical_graph_digest(graph)
    if not isinstance(request_graph_digest, str) or not DIGEST_RE.fullmatch(request_graph_digest) or request_graph_digest != current_graph_digest:
        raise ValueError("request triage request_graph_digest must match the current semantic graph")
    capabilities = triage.get("authority_capabilities")
    if not isinstance(capabilities, list) or len(capabilities) != len(set(capabilities)) or any(value not in AUTHORITY_CAPABILITIES for value in capabilities):
        raise ValueError("request triage authority_capabilities must be a unique controlled list")
    if "authority" in impacts:
        if not capabilities:
            raise ValueError("authority impact requires requested capabilities")
        _, _, spec, _ = load_executor(workflow_dir, node_id)
        if not set(capabilities).issubset(set(spec.get("requires_authority", []))):
            raise ValueError("authority request may include only capabilities declared by the node executor")
    elif capabilities:
        raise ValueError("authority capabilities are allowed only for authority impact")
    surface = json.dumps({"question": question, "alternatives": alternatives, "risks": risks, "triage": triage}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    expected_digest = "sha256:" + hashlib.sha256(surface).hexdigest()
    if digest != expected_digest:
        raise ValueError("request digest does not match its decision surface")
    if not isinstance(digest, str):
        raise ValueError("request requires request_id, sha256 digest, and question")
    value = dict(request)
    value.update(schema_version=2, node_id=node_id, status="pending", created_at=now_utc(), response=None)
    path = workflow_dir / "runtime" / "requests" / f"{request_id}.json"
    if path.exists():
        existing = load_json(path, "confirmation request")
        if not isinstance(existing, dict) or existing.get("digest") != digest:
            raise ValueError("request ID was reused with a different digest")
        return path
    atomic_json(path, value)
    return path


def apply_memory_delta(workflow_dir: Path, repo_root: Path, node_id: str, result: dict[str, Any]) -> None:
    delta = result.get("memory_delta")
    if delta is None:
        return
    path = workflow_dir / "runtime" / "results" / f".{node_id}.memory-delta.json"
    atomic_json(path, delta)
    ok, output = run_checked([sys.executable, str(MEMORY), "--repo-root", str(repo_root), "apply-delta", str(workflow_dir), str(path)])
    if not ok and "stale base_revision" in output:
        state = load_json(workflow_dir / "memory" / "state.json", "memory state")
        if isinstance(state, dict) and isinstance(state.get("revision"), int):
            delta["base_revision"] = state["revision"]
            atomic_json(path, delta)
            ok, output = run_checked([sys.executable, str(MEMORY), "--repo-root", str(repo_root), "apply-delta", str(workflow_dir), str(path)])
    if not ok:
        raise ValueError(f"memory delta rejected: {output}")


def apply_verifier_proposal(
    workflow_dir: Path, repo_root: Path, graph_path: Path, node_id: str, result: dict[str, Any],
) -> None:
    proposal = result.get("verification")
    fields = {"schema_version", "outcome", "challenge_classes", "claims", "limitations"}
    if not isinstance(proposal, dict) or set(proposal) != fields:
        raise ValueError("verifier success requires one exact verification proposal")
    if proposal.get("schema_version") != 1 or proposal.get("outcome") != "pass":
        raise ValueError("automated completion requires a passing schema-version-1 verifier proposal")
    graph = workflow_state.read_graph(graph_path)
    node = workflow_state.node_map(graph).get(node_id)
    if not isinstance(node, dict) or node.get("kind") != "verify":
        raise ValueError("verification proposal is restricted to a configured verify node")
    plan = load_json(workflow_dir / "integrity/verification-plan.json", "verification plan")
    if not isinstance(plan, dict):
        raise ValueError("verification plan must be an object")
    challenges = proposal.get("challenge_classes")
    required_challenges = plan.get("challenge_policy", {}).get("required_classes", [])
    if (
        not isinstance(challenges, list) or len(challenges) != len(set(challenges))
        or any(value not in evidence_runner.CHECK_CLASSES for value in challenges)
        or not set(required_challenges).issubset(challenges)
    ):
        raise ValueError("verifier proposal does not cover the locked challenge policy")
    limitations = proposal.get("limitations")
    if not isinstance(limitations, list) or any(not isinstance(value, str) or not value.strip() for value in limitations):
        raise ValueError("verifier proposal limitations must be a string list")
    critical = [check for check in plan.get("checks", []) if isinstance(check, dict) and check.get("critical") is True]
    critical_paths = [str(check["attestation"]) for check in critical]
    result_paths = {
        item.get("artifact") for item in result.get("evidence", [])
        if isinstance(item, dict) and item.get("kind") == "acceptance" and item.get("exit_code") == 0
    }
    if not set(critical_paths).issubset(result_paths):
        raise ValueError("verifier result does not carry every current critical attestation")
    requirements = {
        str(requirement["id"]): requirement for requirement in graph.get("objective", {}).get("requirements", [])
        if isinstance(requirement, dict) and isinstance(requirement.get("id"), str)
    }
    checks_by_requirement: dict[str, dict[str, str]] = {}
    for check in critical:
        for requirement_id in check.get("requirement_ids", []):
            checks_by_requirement.setdefault(str(requirement_id), {})[str(check["id"])] = str(check["attestation"])
    claims = proposal.get("claims")
    claim_fields = {"id", "requirement_id", "statement", "state", "confidence", "evidence", "limitations"}
    if not isinstance(claims, list) or len(claims) != len(requirements):
        raise ValueError("verifier proposal requires exactly one primary claim per requirement")
    by_requirement: dict[str, dict[str, Any]] = {}
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != claim_fields:
            raise ValueError(f"verifier claim must contain exactly {sorted(claim_fields)!r}")
        requirement_id = claim.get("requirement_id")
        requirement = requirements.get(str(requirement_id))
        if requirement is None or requirement_id in by_requirement:
            raise ValueError("verifier claims must uniquely cover known requirements")
        if (
            claim.get("statement") != requirement.get("text") or claim.get("state") != "verified"
            or claim.get("confidence") not in {"high", "medium"}
            or not isinstance(claim.get("limitations"), list)
            or any(not isinstance(value, str) or not value.strip() for value in claim["limitations"])
        ):
            raise ValueError(f"verifier claim {claim.get('id')} is not calibrated to its requirement")
        evidence = claim.get("evidence")
        allowed = checks_by_requirement.get(str(requirement_id), {})
        if (
            not isinstance(evidence, list) or not evidence
            or any(
                not isinstance(item, dict) or set(item) != {"check", "artifact"}
                or allowed.get(str(item.get("check"))) != item.get("artifact")
                for item in evidence
            )
        ):
            raise ValueError(f"verifier claim {claim.get('id')} lacks matching locked evidence")
        by_requirement[str(requirement_id)] = claim
    if set(by_requirement) != set(requirements):
        raise ValueError("verifier claims do not cover the objective exactly")

    candidate = json.loads(json.dumps(graph))
    candidate["verification"] = {"outcome": "verified", "claims": claims}
    candidate_path = workflow_dir / ".verification-candidate.json"
    atomic_json(candidate_path, candidate)
    try:
        valid, output = run_checked([sys.executable, str(VALIDATOR), str(candidate_path), "--phase", "executable"])
        if not valid:
            raise ValueError(f"verifier proposal does not form a valid graph: {output}")
    finally:
        candidate_path.unlink(missing_ok=True)
    review_input = workflow_dir / "runtime" / "results" / f".{node_id}.verification-review.json"
    duties = plan.get("separation_of_duties", {})
    atomic_json(review_input, {
        "schema_version": 1,
        "verifier_node": node_id,
        "producer_nodes": duties.get("producer_nodes"),
        "outcome": "pass",
        "challenge_classes": challenges,
        "evidence_attestations": critical_paths,
        "limitations": limitations,
    })
    evidence_runner.command_record_review(workflow_dir, repo_root, review_input)
    workflow_state.atomic_write(graph_path, candidate)


def consume_result(workflow_dir: Path, repo_root: Path, graph_path: Path, node_id: str, codex_bin: str) -> str:
    graph = workflow_state.read_graph(graph_path)
    node = workflow_state.node_map(graph)[node_id]
    _, _, spec, result_path = load_executor(workflow_dir, node_id)
    result = load_json(result_path, "node result")
    errors = validate_result(
        result, str(graph.get("workflow_id")), node_id, int(node.get("retry", {}).get("attempts", 0)), str(spec["idempotency_key"]),
    )
    if errors:
        raise ValueError("invalid durable result: " + "; ".join(errors))
    status = str(result["status"])
    contract = workspace_manager.workspace_contract(spec)
    if contract["mode"] != "verifier" and result.get("verification") is not None:
        raise ValueError("only a verifier workspace may return a verification proposal")
    if status == "decompose":
        outcome = decomposition_broker.apply(workflow_dir, repo_root, node_id, result, codex_bin)
        revoke_node_grant(workflow_dir, node_id)
        if outcome["status"] == "waiting_rebase":
            request = store_request(workflow_dir, graph, node_id, {"request": outcome["request"]})
            summary = "Independent decomposition review requires a semantic branch rebase."
            workflow_state.transition(
                arg_namespace(graph_path, node_id, "waiting_user", summary=summary, blocker=f"Confirmation required: {request.name}")
            )
            progress_state.update(workflow_dir, node_id, "waiting", outcome="semantic_rebase", blocker=summary)
            return "waiting_rebase"
        progress_state.update(
            workflow_dir, node_id, "decomposed", outcome="structural_rebase",
            blocker=None,
        )
        return str(outcome["status"])
    if status == "succeeded":
        _, workspace = workspace_manager.resolve(workflow_dir, repo_root, spec, node_id, provision=False, require_clean=False)
        workspace_root = Path(str(workspace["path"])).resolve()
        if contract["mode"] in {"worktree", "integration"}:
            scope_path = workflow_dir / "runtime" / "scope" / f"{node_id}.json"
            scope_report = load_json(scope_path, "scope report")
            workspace_manager.checkpoint(workflow_dir, contract["ref"], node_id, scope_report)
        apply_memory_delta(workflow_dir, workspace_root, node_id, result)
        if contract["mode"] == "verifier":
            apply_verifier_proposal(workflow_dir, workspace_root, graph_path, node_id, result)
        workflow_state.transition(arg_namespace(graph_path, node_id, "complete", summary=result["summary"]))
        revoke_node_grant(workflow_dir, node_id)
        phase = "independently_verified" if contract["mode"] == "verifier" else "accepted"
        progress_state.update(workflow_dir, node_id, phase, workspace_ref=contract["ref"], head_sha=workspace_manager.head(workspace_root) if workspace.get("branch") != "(non-git)" else None)
        if contract["mode"] == "verifier":
            workspace_manager.mark_status(workflow_dir, contract["ref"], "verified")
            registry = workspace_manager.load_registry(workflow_dir)
            source_ref = registry["entries"][contract["ref"]].get("source_ref")
            if isinstance(source_ref, str):
                workspace_manager.mark_status(workflow_dir, source_ref, "integrated")
    elif status in {"waiting_user", "waiting_approval"}:
        request = store_request(workflow_dir, graph, node_id, result)
        workflow_state.transition(arg_namespace(graph_path, node_id, status, summary=result["summary"], blocker=f"Confirmation required: {request.name}"))
        progress_state.update(workflow_dir, node_id, "waiting", outcome=status, blocker=result["summary"])
    elif status == "waiting_external":
        workflow_state.transition(arg_namespace(graph_path, node_id, status, summary=result["summary"], blocker=result["summary"]))
        progress_state.update(workflow_dir, node_id, "waiting", outcome=status, blocker=result["summary"])
    elif status == "blocked":
        workflow_state.transition(arg_namespace(graph_path, node_id, "blocked", summary=result["summary"], blocker=result["summary"]))
        revoke_node_grant(workflow_dir, node_id)
        progress_state.update(workflow_dir, node_id, "rejected", outcome=status, blocker=result["summary"])
    else:
        workflow_state.transition(arg_namespace(graph_path, node_id, "failed", summary=result["summary"], blocker=result["summary"]))
        revoke_node_grant(workflow_dir, node_id)
        progress_state.update(workflow_dir, node_id, "rejected", outcome=status, blocker=result["summary"])
        if contract["mode"] != "primary":
            registry = workspace_manager.load_registry(workflow_dir)
            failed_entry = registry["entries"].get(contract["ref"])
            failed_path = failed_entry.get("path") if isinstance(failed_entry, dict) else None
            disposable = isinstance(failed_path, str) and not workspace_manager.changed_files(Path(failed_path))
            workspace_manager.mark_status(
                workflow_dir, contract["ref"], "rejected-disposable" if disposable else "rejected-dirty",
            )
    return status


def reconcile_durable_results(
    workflow_dir: Path, repo_root: Path, graph_path: Path, events_path: Path, codex_bin: str,
) -> list[str]:
    graph = workflow_state.read_graph(graph_path)
    reconciled: list[str] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("status") != "active":
            continue
        link = node.get("executor") if isinstance(node.get("executor"), dict) else {}
        result_value = link.get("result")
        result_path = workflow_dir / result_value if isinstance(result_value, str) else None
        if result_path is None or not result_path.is_file():
            continue
        node_id = str(node["id"])
        try:
            outcome = consume_result(workflow_dir, repo_root, graph_path, node_id, codex_bin)
        except ValueError as error:
            workflow_state.transition(arg_namespace(graph_path, node_id, "failed", blocker=str(error), summary="Durable result reconciliation failed."))
            outcome = "failed"
        append_event(events_path, {"type": "node_reconciled", "at": now_utc(), "node_id": node_id, "outcome": outcome})
        reconciled.append(node_id)
    return reconciled


def terminal_status(workflow_dir: Path, repo_root: Path, graph_path: Path) -> tuple[str, str | None]:
    graph = workflow_state.read_graph(graph_path)
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict) and node.get("kind") != "expand"]
    statuses = {str(node.get("status")) for node in nodes}
    if nodes and statuses == {"complete"}:
        guard_status, guard_blocker = checkout_gate(workflow_dir, repo_root)
        if guard_status != "clear":
            set_lifecycle(graph_path, "blocked" if guard_status == "blocked" else "waiting")
            return ("blocked" if guard_status == "blocked" else "waiting"), guard_blocker
        set_lifecycle(graph_path, "complete")
        completion_root = completion_repo_root(workflow_dir, repo_root)
        checks = [
            [sys.executable, str(VALIDATOR), str(graph_path), "--phase", "complete"],
            [sys.executable, str(MEMORY), "--repo-root", str(completion_root), "validate", str(workflow_dir), "--phase", "complete", "--check-artifacts"],
            [sys.executable, str(EVIDENCE), "validate", str(workflow_dir), "--phase", "complete", "--repo-root", str(completion_root)],
        ]
        failures = [output for ok, output in (run_checked(argv) for argv in checks) if not ok]
        if not failures:
            plan = load_json(workflow_dir / "integrity" / "verification-plan.json", "verification plan")
            external = plan.get("external_gate") if isinstance(plan, dict) and isinstance(plan.get("external_gate"), dict) else {}
            if external.get("required") is True and external.get("status") == "passed":
                duties = plan.get("separation_of_duties") if isinstance(plan.get("separation_of_duties"), dict) else {}
                for verifier_node in duties.get("verifier_nodes", []):
                    if isinstance(verifier_node, str):
                        progress_state.update(workflow_dir, verifier_node, "externally_verified", outcome="passed")
            workspace_modes: dict[str, str] = {}
            for node in nodes:
                node_id = str(node.get("id"))
                _, _, spec, _ = load_executor(workflow_dir, node_id)
                workspace_modes[node_id] = workspace_manager.workspace_contract(spec)["mode"]
            failures.extend(progress_state.validate_completion(workflow_dir, graph, workspace_modes))
            if not failures:
                guard_status, guard_blocker = checkout_gate(workflow_dir, repo_root)
                if guard_status != "clear":
                    set_lifecycle(graph_path, "blocked" if guard_status == "blocked" else "waiting")
                    return ("blocked" if guard_status == "blocked" else "waiting"), guard_blocker
                delivery = delivery_broker.advance(workflow_dir, repo_root)
                if delivery["status"] in {"not_required", "published"}:
                    return "complete", None
                if delivery["status"] in {"waiting_approval", "waiting_external"}:
                    return "waiting", delivery.get("failure") or "Authorized Ship delivery is waiting."
                return "blocked", delivery.get("failure") or "Ship delivery is blocked."
        set_lifecycle(graph_path, "blocked")
        return "blocked", "Completion gates failed: " + " | ".join(failures)
    if statuses & {"waiting_user", "waiting_approval", "waiting_external"}:
        set_lifecycle(graph_path, "waiting")
        return "waiting", None
    if statuses & {"blocked", "failed", "stale"}:
        set_lifecycle(graph_path, "blocked")
        return "blocked", "At least one required node is blocked, failed, or stale."
    set_lifecycle(graph_path, "active")
    return "active", None


def completion_repo_root(workflow_dir: Path, fallback: Path) -> Path:
    try:
        registry = workspace_manager.load_registry(workflow_dir)
    except ValueError:
        return fallback
    candidates = [
        entry for entry in registry["entries"].values()
        if isinstance(entry, dict) and entry.get("mode") in {"verifier", "integration"} and isinstance(entry.get("path"), str)
    ]
    candidates.sort(key=lambda entry: 0 if entry.get("mode") == "verifier" else 1)
    return Path(candidates[0]["path"]).resolve() if candidates else fallback


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workflow_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--codex-bin", default=shutil.which("codex") or "codex")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recover-stale-lease", action="store_true")
    parser.add_argument("--stale-lease-seconds", type=int, default=300)
    args = parser.parse_args()
    workflow_dir = args.workflow_dir.resolve()
    repo_root = args.repo_root.resolve()
    graph_path = workflow_dir / "graph.json"
    events_path = workflow_dir / "runtime" / "events.jsonl"
    lease = Lease(workflow_dir, args.recover_stale_lease, args.stale_lease_seconds)
    try:
        decomposition_recovery: list[dict[str, str]] = []
        if not args.dry_run:
            lease.acquire()
            decomposition_recovery = decomposition_broker.recover_pending(workflow_dir, repo_root)
        ok, output = run_checked([sys.executable, str(VALIDATOR), str(graph_path), "--phase", "executable"])
        if not ok:
            raise ValueError(f"graph is not executable: {output}")
        ok, output = run_checked([sys.executable, str(QUESTION_GATE), "validate", str(workflow_dir)])
        if not ok:
            raise ValueError(f"question gate is not locked: {output}")
        graph = workflow_state.read_graph(graph_path)
        verify_executors(workflow_dir, graph)
        if args.dry_run:
            print(json.dumps({"workflow_id": graph.get("workflow_id"), "ready": workflow_state.ready_ids(graph), "goal_required": False}, indent=2))
            return 0
        guard_exit = stop_if_checkout_drifted(workflow_dir, repo_root, graph, events_path)
        if guard_exit is not None:
            return guard_exit
        reconciled = reconcile_durable_results(workflow_dir, repo_root, graph_path, events_path, args.codex_bin)
        recovered = reconcile_lost_active(graph_path)
        append_event(events_path, {
            "type": "runner_started", "at": now_utc(), "pid": os.getpid(), "reconciled": reconciled,
            "recovered": recovered, "decomposition_recovery": decomposition_recovery,
        })
        save_runtime(workflow_dir, graph, "active")
        batches = 0
        while True:
            lease.heartbeat()
            graph = workflow_state.read_graph(graph_path)
            guard_exit = stop_if_checkout_drifted(workflow_dir, repo_root, graph, events_path)
            if guard_exit is not None:
                return guard_exit
            ensure_authority_requests(workflow_dir, graph_path)
            resumed = approved_resumes(workflow_dir, repo_root, graph_path)
            graph = workflow_state.read_graph(graph_path)
            max_parallel = int(graph.get("constraints", {}).get("max_parallel", 1))
            workflow_resumes = workflow_scoped_resumes(resumed)
            if has_pending_workflow_request(workflow_dir):
                candidates = []
            elif workflow_resumes:
                candidates = workflow_resumes[:1]
            else:
                candidates = resumed + [
                    (node_id, None) for node_id in workflow_state.ready_ids(graph) if node_id not in {item[0] for item in resumed}
                ]
            selected = select_safe_frontier(workflow_dir, repo_root, graph, candidates, max_parallel)
            if not selected:
                guard_exit = stop_if_checkout_drifted(workflow_dir, repo_root, graph, events_path)
                if guard_exit is not None:
                    return guard_exit
                status, blocker = terminal_status(workflow_dir, repo_root, graph_path)
                save_runtime(workflow_dir, workflow_state.read_graph(graph_path), status, blocker)
                append_event(events_path, {"type": "runner_stopped", "at": now_utc(), "status": status, "blocker": blocker})
                print(json.dumps({"workflow_id": graph.get("workflow_id"), "status": status, "blocker": blocker}, indent=2))
                return 0 if status in {"complete", "waiting"} else 1
            for node_id, confirmation in selected:
                _, _, selected_spec, _ = load_executor(workflow_dir, node_id)
                selected_contract = workspace_manager.workspace_contract(selected_spec)
                progress_state.update(workflow_dir, node_id, "queued", workspace_ref=selected_contract["ref"])
                if confirmation is None:
                    workflow_state.transition(arg_namespace(graph_path, node_id, "active", agent="node-runner", increment_attempt=True))
                else:
                    request = load_json(confirmation, "confirmation request")
                    if not isinstance(request, dict) or request.get("status") != "approved":
                        raise ValueError(f"confirmation for node {node_id} is no longer approved")
                    request["status"] = "consumed"
                    request["consumed_at"] = now_utc()
                    atomic_json(confirmation, request)
                    workflow_state.transition(arg_namespace(graph_path, node_id, "active", summary="Resuming with digest-bound confirmation."))
                append_event(events_path, {"type": "node_dispatched", "at": now_utc(), "node_id": node_id, "confirmation": confirmation.name if confirmation else None})
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(selected)) as pool:
                futures = [pool.submit(execute_node, workflow_dir, repo_root, node_id, args.codex_bin, confirmation) for node_id, confirmation in selected]
                completed_nodes = []
                for future in concurrent.futures.as_completed(futures):
                    finished = future.result()
                    completed_nodes.append(finished)
                    progress_state.update(
                        workflow_dir, finished[0], "executor_exited", exit_code=finished[1],
                        outcome="process_success" if finished[1] == 0 else "process_failed",
                    )
            guard_exit = stop_if_checkout_drifted(workflow_dir, repo_root, workflow_state.read_graph(graph_path), events_path)
            if guard_exit is not None:
                return guard_exit
            for node_id, exit_code, detail in completed_nodes:
                try:
                    outcome = consume_result(workflow_dir, repo_root, graph_path, node_id, args.codex_bin)
                except ValueError as error:
                    workflow_state.transition(arg_namespace(graph_path, node_id, "failed", blocker=str(error), summary="Runner rejected the node result."))
                    outcome = "failed"
                    detail = f"{detail}; {error}"
                    progress_state.update(workflow_dir, node_id, "rejected", outcome="runner_rejected", blocker=str(error))
                append_event(events_path, {"type": "node_finished", "at": now_utc(), "node_id": node_id, "exit_code": exit_code, "outcome": outcome, "detail": detail[-1000:]})
            batches += 1
            if args.once and batches >= 1:
                guard_exit = stop_if_checkout_drifted(workflow_dir, repo_root, workflow_state.read_graph(graph_path), events_path, once=True)
                if guard_exit is not None:
                    return guard_exit
                status, blocker = terminal_status(workflow_dir, repo_root, graph_path)
                save_runtime(workflow_dir, workflow_state.read_graph(graph_path), status, blocker)
                append_event(events_path, {"type": "runner_stopped", "at": now_utc(), "status": status, "once": True})
                print(json.dumps({"workflow_id": graph.get("workflow_id"), "status": status, "batches": batches}, indent=2))
                return 0 if status != "blocked" else 1
    except ValueError as error:
        parser.error(str(error))
    finally:
        lease.release()


if __name__ == "__main__":
    raise SystemExit(main())
