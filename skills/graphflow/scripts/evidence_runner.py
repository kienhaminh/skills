#!/usr/bin/env python3
"""Lock workflow oracles and issue reproducible, current-state attestations."""

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
import time
from pathlib import Path, PurePosixPath
from typing import Any


RUNNER_ID = "workflow-evidence-runner-v1"
PLAN_FIELDS = {
    "schema_version", "workflow_id", "level", "checks", "challenge_policy",
    "separation_of_duties", "external_gate",
}
CHECK_FIELDS = {
    "id", "requirement_ids", "critical", "class", "argv", "cwd", "env",
    "expected_exit", "timeout_seconds", "watch", "attestation", "verifier_node",
}
CHECK_CLASSES = {
    "primary", "negative", "boundary", "integration", "mutation",
    "metamorphic", "differential", "permission",
}
LEVELS = {"low", "medium", "high"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SECRET_KEY_RE = re.compile(r"(?i)(password|secret|token|api[_-]?key|credential)")
SAFE_ENV = {"PATH", "LANG", "LC_ALL", "TMPDIR", "TZ", "CI", "NODE_ENV"}
MAX_LOG_BYTES = 2_000_000
INTEGRITY_CONFIG = {
    "schema_version": 1,
    "verification_plan": "integrity/verification-plan.json",
    "lock": "integrity/lock.json",
    "runner": RUNNER_ID,
    "evidence_dir": "evidence/attestations",
    "completion_rule": "all-critical",
}
LOCK_FIELDS = {
    "schema_version", "workflow_id", "status", "plan_digest", "runner_digest",
    "contract_digest", "locked_at",
}
EXTERNAL_FIELDS = {"required", "status", "artifact", "digest", "provenance"}
PROVENANCE_FIELDS = {"provider", "repository", "commit_sha", "workflow_id", "run_id", "url", "attestation_digest", "protected"}


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


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def file_digest(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def json_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256_bytes(encoded)


def canonical_graph_digest(graph: dict[str, Any]) -> str:
    semantic = json.loads(json.dumps(graph))
    semantic.pop("lifecycle", None)
    semantic.pop("verification", None)
    for node in semantic.get("nodes", []):
        if isinstance(node, dict):
            for field in ("status", "runtime", "retry"):
                node.pop(field, None)
    return json_digest(semantic)


def normalized_relative(value: Any) -> str | None:
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


def node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        node.get("id"): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }


def requirement_ids(graph: dict[str, Any]) -> set[str]:
    objective = graph.get("objective") if isinstance(graph.get("objective"), dict) else {}
    return {
        item.get("id")
        for item in objective.get("requirements", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def validate_graph(graph_path: Path, phase: str) -> None:
    validator = Path(__file__).with_name("validate_graph.py")
    completed = subprocess.run(
        [sys.executable, str(validator), str(graph_path), "--phase", phase, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise ValueError(f"graph validation failed: {(completed.stdout + completed.stderr).strip()}")


def resolve_under(root: Path, relative: str) -> Path:
    candidate = root / relative
    try:
        candidate.resolve(strict=False).relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"path escapes root: {relative}") from error
    return candidate


def load_workflow(workflow_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Path]]:
    graph_path = workflow_dir / "graph.json"
    graph = load_json(graph_path, "graph.json")
    if not isinstance(graph, dict):
        raise ValueError("graph root must be an object")
    integrity = graph.get("integrity")
    if not isinstance(integrity, dict):
        raise ValueError("graph integrity must be an object")
    for field, expected in INTEGRITY_CONFIG.items():
        if integrity.get(field) != expected:
            raise ValueError(f"graph integrity.{field} must equal {expected!r}")
    plan_path = workflow_dir / INTEGRITY_CONFIG["verification_plan"]
    lock_path = workflow_dir / INTEGRITY_CONFIG["lock"]
    plan = load_json(plan_path, "verification plan")
    lock = load_json(lock_path, "integrity lock")
    return graph, plan, lock, {"graph": graph_path, "plan": plan_path, "lock": lock_path}


def weak_oracle(argv: list[str]) -> bool:
    executable = Path(argv[0]).name.lower()
    if executable in {"true", "echo", "printf"}:
        return True
    if executable in {"sh", "bash", "zsh", "fish"} and "-c" in argv:
        return True
    if executable.startswith("python") and "-c" in argv:
        index = argv.index("-c")
        code = argv[index + 1].strip().replace(" ", "") if index + 1 < len(argv) else ""
        if code in {"pass", "exit(0)", "sys.exit(0)", "raiseSystemExit(0)"}:
            return True
    return False


def validate_plan(plan: Any, graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["plan: root must be an object"]
    if set(plan) != PLAN_FIELDS:
        errors.append(f"plan: must contain exactly {sorted(PLAN_FIELDS)!r}")
    if plan.get("schema_version") != 1:
        errors.append("plan.schema_version: must equal 1")
    if plan.get("workflow_id") != graph.get("workflow_id"):
        errors.append("plan.workflow_id: must match graph")
    level = plan.get("level")
    if level not in LEVELS or level != (graph.get("integrity") or {}).get("level"):
        errors.append("plan.level: must match graph integrity.level")
    nodes = node_map(graph)
    requirements = requirement_ids(graph)
    checks = plan.get("checks")
    check_values: list[dict[str, Any]] = []
    ids: set[str] = set()
    if not isinstance(checks, list) or not checks:
        errors.append("plan.checks: must be a non-empty list")
    else:
        for index, check in enumerate(checks):
            where = f"plan.checks[{index}]"
            if not isinstance(check, dict):
                errors.append(f"{where}: must be an object")
                continue
            check_values.append(check)
            if set(check) != CHECK_FIELDS:
                errors.append(f"{where}: must contain exactly {sorted(CHECK_FIELDS)!r}")
            check_id = check.get("id")
            if not isinstance(check_id, str) or not ID_RE.fullmatch(check_id) or check_id in ids:
                errors.append(f"{where}.id: must be a unique stable identifier")
            else:
                ids.add(check_id)
            covered = check.get("requirement_ids")
            if not isinstance(covered, list) or not covered or len(covered) != len(set(covered)) or any(value not in requirements for value in covered):
                errors.append(f"{where}.requirement_ids: must contain unique existing requirements")
            if not isinstance(check.get("critical"), bool):
                errors.append(f"{where}.critical: must be a boolean")
            if check.get("class") not in CHECK_CLASSES:
                errors.append(f"{where}.class: unknown check class")
            argv = check.get("argv")
            if not isinstance(argv, list) or not argv or any(not isinstance(value, str) or not value for value in argv):
                errors.append(f"{where}.argv: must be a non-empty literal string list")
            elif weak_oracle(argv):
                errors.append(f"{where}.argv: trivial or shell-mediated oracle is forbidden")
            if check.get("cwd") not in {"repo", "workflow"}:
                errors.append(f"{where}.cwd: must be repo or workflow")
            env = check.get("env")
            if not isinstance(env, dict):
                errors.append(f"{where}.env: must be an object")
            else:
                for key, value in env.items():
                    if not isinstance(key, str) or not key or SECRET_KEY_RE.search(key) or not isinstance(value, str) or len(value) > 256:
                        errors.append(f"{where}.env: keys and literal values must be sanitized")
            expected_exit = check.get("expected_exit")
            if not isinstance(expected_exit, int) or isinstance(expected_exit, bool) or expected_exit < 0 or expected_exit > 255:
                errors.append(f"{where}.expected_exit: must be an integer from 0 to 255")
            timeout = check.get("timeout_seconds")
            if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 3600:
                errors.append(f"{where}.timeout_seconds: must be from 1 to 3600")
            watch = check.get("watch")
            if not isinstance(watch, list) or not watch:
                errors.append(f"{where}.watch: must be a non-empty list")
            else:
                seen_watch: set[tuple[str, str]] = set()
                for watch_index, item in enumerate(watch):
                    watch_where = f"{where}.watch[{watch_index}]"
                    if not isinstance(item, dict) or set(item) != {"root", "path"} or item.get("root") not in {"repo", "workflow"}:
                        errors.append(f"{watch_where}: must contain root=repo|workflow and path")
                        continue
                    path = normalized_relative(item.get("path"))
                    key = (str(item.get("root")), str(item.get("path")))
                    if path is None or path != item.get("path") or key in seen_watch:
                        errors.append(f"{watch_where}.path: must be unique, normalized, and explicit")
                    seen_watch.add(key)
            attestation = normalized_relative(check.get("attestation"))
            if attestation != check.get("attestation") or not isinstance(attestation, str) or not attestation.startswith("evidence/attestations/") or not attestation.endswith(".json"):
                errors.append(f"{where}.attestation: must be a JSON path under evidence/attestations")
            verifier = check.get("verifier_node")
            if verifier not in nodes or nodes.get(verifier, {}).get("kind") != "verify":
                errors.append(f"{where}.verifier_node: must reference a verify node")
            elif isinstance(attestation, str):
                scopes = nodes[verifier].get("scope") if isinstance(nodes[verifier].get("scope"), dict) else {}
                if not any(isinstance(owned, str) and paths_overlap(owned, attestation) for owned in scopes.get("artifacts", [])):
                    errors.append(f"{where}.attestation: verifier node does not own this artifact path")

    critical_coverage = {
        requirement
        for check in check_values if check.get("critical") is True
        for requirement in check.get("requirement_ids", []) if isinstance(requirement, str)
    }
    missing_coverage = sorted(requirements - critical_coverage)
    if missing_coverage:
        errors.append(f"plan.checks: critical checks do not cover {missing_coverage!r}")

    challenge = plan.get("challenge_policy")
    required_classes: list[str] = []
    mutation_required = None
    if not isinstance(challenge, dict) or set(challenge) != {"required_classes", "mutation_required"}:
        errors.append("plan.challenge_policy: must contain exactly required_classes and mutation_required")
    else:
        required_classes = challenge.get("required_classes")
        mutation_required = challenge.get("mutation_required")
        minimum = {"low": 1, "medium": 2, "high": 3}.get(level, 99)
        if not isinstance(required_classes, list) or len(required_classes) < minimum or len(required_classes) != len(set(required_classes)) or any(value not in CHECK_CLASSES - {"primary"} for value in required_classes):
            errors.append(f"plan.challenge_policy.required_classes: level {level!r} needs at least {minimum} unique challenge classes")
            required_classes = []
        if not isinstance(mutation_required, bool):
            errors.append("plan.challenge_policy.mutation_required: must be a boolean")
        elif level == "high" and mutation_required is not True:
            errors.append("plan.challenge_policy.mutation_required: high integrity requires mutation testing")
    critical_classes = {check.get("class") for check in check_values if check.get("critical") is True}
    if set(required_classes) - critical_classes:
        errors.append("plan.challenge_policy: every required class needs a critical check")
    if mutation_required is True and "mutation" not in critical_classes:
        errors.append("plan.challenge_policy: mutation_required needs a critical mutation check")

    duties = plan.get("separation_of_duties")
    producer_nodes: list[str] = []
    verifier_nodes: list[str] = []
    quorum = None
    if not isinstance(duties, dict) or set(duties) != {"producer_nodes", "verifier_nodes", "min_independent_verifiers"}:
        errors.append("plan.separation_of_duties: has invalid fields")
    else:
        producer_nodes = duties.get("producer_nodes")
        verifier_nodes = duties.get("verifier_nodes")
        quorum = duties.get("min_independent_verifiers")
        if not isinstance(producer_nodes, list) or not producer_nodes or len(producer_nodes) != len(set(producer_nodes)) or any(value not in nodes or nodes[value].get("kind") == "verify" for value in producer_nodes):
            errors.append("plan.separation_of_duties.producer_nodes: must be unique non-verifier nodes")
            producer_nodes = []
        if not isinstance(verifier_nodes, list) or not verifier_nodes or len(verifier_nodes) != len(set(verifier_nodes)) or any(value not in nodes or nodes[value].get("kind") != "verify" for value in verifier_nodes):
            errors.append("plan.separation_of_duties.verifier_nodes: must be unique verify nodes")
            verifier_nodes = []
        if set(producer_nodes) & set(verifier_nodes):
            errors.append("plan.separation_of_duties: producers and verifiers must be disjoint")
        minimum_quorum = 2 if level == "high" else 1
        if not isinstance(quorum, int) or isinstance(quorum, bool) or quorum < minimum_quorum or quorum > len(verifier_nodes):
            errors.append(f"plan.separation_of_duties.min_independent_verifiers: level {level!r} needs at least {minimum_quorum}")
    for check in check_values:
        if check.get("verifier_node") not in verifier_nodes:
            errors.append(f"plan.checks[{check.get('id')}].verifier_node: must be in separation_of_duties.verifier_nodes")

    external = plan.get("external_gate")
    if not isinstance(external, dict) or set(external) != EXTERNAL_FIELDS:
        errors.append("plan.external_gate: has invalid fields")
    else:
        required = external.get("required")
        status = external.get("status")
        artifact = external.get("artifact")
        digest = external.get("digest")
        provenance = external.get("provenance")
        if not isinstance(required, bool):
            errors.append("plan.external_gate.required: must be a boolean")
        elif required:
            if status not in {"pending", "passed"}:
                errors.append("plan.external_gate.status: required gate must be pending or passed")
            if level != "high":
                errors.append("plan.external_gate.required: only high integrity may require an external gate")
            if status == "passed":
                if normalized_relative(artifact) != artifact or not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
                    errors.append("plan.external_gate: passed gate needs a normalized artifact and digest")
                if not isinstance(provenance, dict) or set(provenance) != PROVENANCE_FIELDS:
                    errors.append("plan.external_gate.provenance: passed gate needs exact provider provenance")
                else:
                    for field in ("provider", "repository", "workflow_id", "run_id"):
                        if not isinstance(provenance.get(field), str) or not provenance[field].strip():
                            errors.append(f"plan.external_gate.provenance.{field}: must be non-empty")
                    if not isinstance(provenance.get("commit_sha"), str) or not re.fullmatch(r"[0-9a-f]{40,64}", provenance["commit_sha"]):
                        errors.append("plan.external_gate.provenance.commit_sha: must be an exact Git SHA")
                    if not isinstance(provenance.get("url"), str) or not provenance["url"].startswith("https://"):
                        errors.append("plan.external_gate.provenance.url: must be an HTTPS provider URL")
                    if not isinstance(provenance.get("attestation_digest"), str) or not DIGEST_RE.fullmatch(provenance["attestation_digest"]):
                        errors.append("plan.external_gate.provenance.attestation_digest: must be sha256")
                    if provenance.get("protected") is not True:
                        errors.append("plan.external_gate.provenance.protected: must be true")
            elif provenance is not None:
                errors.append("plan.external_gate.provenance: pending gate must be null")
        elif status != "not_required" or artifact is not None or digest is not None or provenance is not None:
            errors.append("plan.external_gate: optional gate must be not_required with null artifact/digest/provenance")
        if level == "high" and required is not True:
            errors.append("plan.external_gate.required: high integrity requires an external gate")
    return errors


def runner_digest() -> str:
    return file_digest(Path(__file__).resolve())


def validate_lock(
    graph: dict[str, Any],
    plan: dict[str, Any],
    lock: Any,
    *,
    complete: bool,
    workflow_dir: Path | None = None,
) -> list[str]:
    errors = validate_plan(plan, graph)
    if not isinstance(lock, dict) or set(lock) != LOCK_FIELDS:
        return [*errors, f"lock: must contain exactly {sorted(LOCK_FIELDS)!r}"]
    expected_plan = json_digest(plan)
    expected_runner = runner_digest()
    expected_contract = canonical_graph_digest(graph)
    integrity = graph.get("integrity") if isinstance(graph.get("integrity"), dict) else {}
    expected = {
        "schema_version": 1,
        "workflow_id": graph.get("workflow_id"),
        "status": "locked",
        "plan_digest": expected_plan,
        "runner_digest": expected_runner,
        "contract_digest": expected_contract,
    }
    for field, value in expected.items():
        if lock.get(field) != value:
            errors.append(f"lock.{field}: does not match current locked contract")
    if not isinstance(lock.get("locked_at"), str) or not lock.get("locked_at"):
        errors.append("lock.locked_at: must be a timestamp")
    for field, value in (("status", "locked"), ("plan_digest", expected_plan), ("runner_digest", expected_runner)):
        if integrity.get(field) != value:
            errors.append(f"graph.integrity.{field}: does not match current locked contract")
    external = plan.get("external_gate") if isinstance(plan.get("external_gate"), dict) else {}
    if complete and external.get("required") is True:
        artifact = external.get("artifact")
        path = resolve_under(workflow_dir, artifact) if workflow_dir is not None and isinstance(artifact, str) else None
        if external.get("status") != "passed" or path is None or not path.is_file() or file_digest(path) != external.get("digest"):
            errors.append("plan.external_gate: required external gate is not current and passed")
        elif path is not None:
            artifact_value = load_json(path, "external gate artifact")
            expected_provenance = external.get("provenance")
            if not isinstance(artifact_value, dict) or artifact_value.get("status") != "passed" or artifact_value.get("provenance") != expected_provenance:
                errors.append("plan.external_gate: artifact does not match protected provider provenance")
    return errors


def state_digest(workflow_dir: Path, repo_root: Path, watch: list[dict[str, str]]) -> str:
    records: list[dict[str, Any]] = []
    for item in sorted(watch, key=lambda value: (value["root"], value["path"])):
        root = repo_root if item["root"] == "repo" else workflow_dir
        path = resolve_under(root, item["path"])
        prefix = f"{item['root']}:{item['path']}"
        if not path.exists() and not path.is_symlink():
            records.append({"path": prefix, "type": "missing"})
            continue
        candidates = [path]
        if path.is_dir() and not path.is_symlink():
            candidates.extend(sorted(path.rglob("*"), key=lambda value: value.as_posix()))
        for candidate in candidates:
            relative = candidate.relative_to(root).as_posix()
            label = f"{item['root']}:{relative}"
            if candidate.is_symlink():
                records.append({"path": label, "type": "symlink", "target": os.readlink(candidate)})
            elif candidate.is_dir():
                records.append({"path": label, "type": "directory"})
            elif candidate.is_file():
                records.append({"path": label, "type": "file", "digest": file_digest(candidate)})
            else:
                records.append({"path": label, "type": "other"})
    return json_digest(records)


def expanded_argv(argv: list[str], workflow_dir: Path, repo_root: Path) -> list[str]:
    replacements = {"{workflow_dir}": str(workflow_dir), "{repo_root}": str(repo_root)}
    return [replacements.get(value, value) for value in argv]


def expected_attestation(check: dict[str, Any], plan_digest: str, contract_digest: str) -> dict[str, Any]:
    return {
        "runner": RUNNER_ID,
        "runner_digest": runner_digest(),
        "check_id": check["id"],
        "plan_digest": plan_digest,
        "contract_digest": contract_digest,
    }


def validate_attestation(
    workflow_dir: Path,
    repo_root: Path,
    check: dict[str, Any],
    plan_digest: str,
    contract_digest: str,
) -> list[str]:
    errors: list[str] = []
    path = resolve_under(workflow_dir, check["attestation"])
    if not path.is_file():
        return [f"attestation {check['id']}: missing {check['attestation']}"]
    value = load_json(path, f"attestation {check['id']}")
    if not isinstance(value, dict):
        return [f"attestation {check['id']}: root must be an object"]
    for field, expected in expected_attestation(check, plan_digest, contract_digest).items():
        if value.get(field) != expected:
            errors.append(f"attestation {check['id']}.{field}: does not match current contract")
    expected_argv = expanded_argv(check["argv"], workflow_dir, repo_root)
    expected_cwd = str(repo_root if check["cwd"] == "repo" else workflow_dir)
    if value.get("argv") != expected_argv or value.get("cwd") != expected_cwd:
        errors.append(f"attestation {check['id']}: command context does not match plan")
    if value.get("expected_exit") != check["expected_exit"] or value.get("exit_code") != check["expected_exit"]:
        errors.append(f"attestation {check['id']}: exit result does not match plan")
    if value.get("timed_out") is not False or value.get("output_truncated") is not False or value.get("passed") is not True or value.get("state_mutated") is not False:
        errors.append(f"attestation {check['id']}: must be passed, current, unmutated, and not timed out")
    for stream in ("stdout", "stderr"):
        descriptor = value.get(stream)
        if not isinstance(descriptor, dict) or set(descriptor) != {"path", "digest"}:
            errors.append(f"attestation {check['id']}.{stream}: invalid descriptor")
            continue
        relative = normalized_relative(descriptor.get("path"))
        log_path = resolve_under(workflow_dir, relative) if relative == descriptor.get("path") and isinstance(relative, str) else None
        if log_path is None or not log_path.is_file() or file_digest(log_path) != descriptor.get("digest"):
            errors.append(f"attestation {check['id']}.{stream}: log missing or digest mismatch")
    current_state = state_digest(workflow_dir, repo_root, check["watch"])
    if value.get("watch_digest_before") != current_state or value.get("watch_digest_after") != current_state:
        errors.append(f"attestation {check['id']}: watched state changed or is stale")
    return errors


def command_lock(workflow_dir: Path, repo_root: Path) -> dict[str, Any]:
    graph, plan, lock, paths = load_workflow(workflow_dir)
    validate_graph(paths["graph"], "draft")
    plan_value = json_digest(plan)
    runner_value = runner_digest()
    existing_status = lock.get("status") if isinstance(lock, dict) else None
    if existing_status == "locked":
        current_errors = validate_lock(graph, plan, lock, complete=False, workflow_dir=workflow_dir)
        if current_errors:
            raise ValueError("locked oracle changed; create a new baseline or obtain explicit supersession: " + "; ".join(current_errors))
        return {"status": "locked", "idempotent": True, "plan_digest": plan_value, "runner_digest": runner_value, "contract_digest": lock["contract_digest"]}
    if existing_status != "template":
        raise ValueError("lock status must be template for initial lock")
    errors = validate_plan(plan, graph)
    if errors:
        raise ValueError("; ".join(errors))
    graph_integrity = graph["integrity"]
    graph_integrity["status"] = "locked"
    graph_integrity["plan_digest"] = plan_value
    graph_integrity["runner_digest"] = runner_value
    contract_value = canonical_graph_digest(graph)
    lock_value = {
        "schema_version": 1,
        "workflow_id": graph.get("workflow_id"),
        "status": "locked",
        "plan_digest": plan_value,
        "runner_digest": runner_value,
        "contract_digest": contract_value,
        "locked_at": now_utc(),
    }
    atomic_json(paths["graph"], graph)
    atomic_json(paths["lock"], lock_value)
    return {"status": "locked", "idempotent": False, "plan_digest": plan_value, "runner_digest": runner_value, "contract_digest": contract_value}


def load_locked(workflow_dir: Path, repo_root: Path, graph_phase: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Path]]:
    graph, plan, lock, paths = load_workflow(workflow_dir)
    validate_graph(paths["graph"], graph_phase)
    errors = validate_lock(graph, plan, lock, complete=graph_phase == "complete", workflow_dir=workflow_dir)
    if errors:
        raise ValueError("; ".join(errors))
    return graph, plan, lock, paths


def command_run(workflow_dir: Path, repo_root: Path, check_id: str) -> dict[str, Any]:
    graph, plan, lock, _ = load_locked(workflow_dir, repo_root, "executable")
    check = next((value for value in plan["checks"] if value.get("id") == check_id), None)
    if check is None:
        raise ValueError(f"unknown check {check_id}")
    before = state_digest(workflow_dir, repo_root, check["watch"])
    argv = expanded_argv(check["argv"], workflow_dir, repo_root)
    cwd = repo_root if check["cwd"] == "repo" else workflow_dir
    environment = {key: value for key, value in os.environ.items() if key in SAFE_ENV}
    environment.update(check["env"])
    started_at = now_utc()
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=environment,
            capture_output=True,
            check=False,
            timeout=check["timeout_seconds"],
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        exit_code = None
        stdout = error.stdout or b""
        stderr = error.stderr or b""
    output_truncated = len(stdout) > MAX_LOG_BYTES or len(stderr) > MAX_LOG_BYTES
    stdout = stdout[:MAX_LOG_BYTES]
    stderr = stderr[:MAX_LOG_BYTES]
    duration_ms = int((time.monotonic() - started) * 1000)
    after = state_digest(workflow_dir, repo_root, check["watch"])
    logs_dir = workflow_dir / "evidence" / "attestations" / "logs"
    stdout_relative = f"evidence/attestations/logs/{check_id}.stdout.log"
    stderr_relative = f"evidence/attestations/logs/{check_id}.stderr.log"
    stdout_path = workflow_dir / stdout_relative
    stderr_path = workflow_dir / stderr_relative
    atomic_bytes(stdout_path, stdout)
    atomic_bytes(stderr_path, stderr)
    passed = not timed_out and not output_truncated and exit_code == check["expected_exit"] and before == after
    envelope = {
        "schema_version": 1,
        **expected_attestation(check, lock["plan_digest"], lock["contract_digest"]),
        "requirement_ids": check["requirement_ids"],
        "class": check["class"],
        "critical": check["critical"],
        "verifier_node": check["verifier_node"],
        "argv": argv,
        "cwd": str(cwd),
        "started_at": started_at,
        "finished_at": now_utc(),
        "duration_ms": duration_ms,
        "expected_exit": check["expected_exit"],
        "exit_code": exit_code,
        "timed_out": timed_out,
        "output_truncated": output_truncated,
        "stdout": {"path": stdout_relative, "digest": file_digest(stdout_path)},
        "stderr": {"path": stderr_relative, "digest": file_digest(stderr_path)},
        "watch_digest_before": before,
        "watch_digest_after": after,
        "state_mutated": before != after,
        "passed": passed,
    }
    attestation_path = resolve_under(workflow_dir, check["attestation"])
    atomic_json(attestation_path, envelope)
    if not passed:
        raise ValueError(f"check {check_id} failed: exit={exit_code}, expected={check['expected_exit']}, timed_out={timed_out}, output_truncated={output_truncated}, state_mutated={before != after}")
    return {"check_id": check_id, "passed": True, "attestation": check["attestation"], "digest": file_digest(attestation_path)}


def validate_review(
    review: Any,
    graph: dict[str, Any],
    plan: dict[str, Any],
    lock: dict[str, Any],
    workflow_dir: Path,
) -> list[str]:
    errors: list[str] = []
    fields = {
        "schema_version", "runner", "runner_digest", "plan_digest", "contract_digest",
        "verifier_node", "producer_nodes", "outcome", "challenge_classes",
        "evidence_attestations", "limitations", "recorded_at",
    }
    if not isinstance(review, dict) or set(review) != fields:
        return [f"review: must contain exactly {sorted(fields)!r}"]
    duties = plan["separation_of_duties"]
    if review.get("schema_version") != 1 or review.get("runner") != RUNNER_ID:
        errors.append("review: invalid schema or runner")
    if review.get("runner_digest") != runner_digest() or review.get("plan_digest") != lock["plan_digest"] or review.get("contract_digest") != lock["contract_digest"]:
        errors.append("review: stale runner, plan, or contract digest")
    verifier = review.get("verifier_node")
    if verifier not in duties["verifier_nodes"] or node_map(graph).get(verifier, {}).get("kind") != "verify":
        errors.append("review.verifier_node: must be an independent configured verifier")
    if review.get("producer_nodes") != duties["producer_nodes"] or verifier in review.get("producer_nodes", []):
        errors.append("review.producer_nodes: must equal the locked producer set and exclude verifier")
    if review.get("outcome") not in {"pass", "fail"}:
        errors.append("review.outcome: must be pass or fail")
    challenges = review.get("challenge_classes")
    if not isinstance(challenges, list) or len(challenges) != len(set(challenges)) or any(value not in CHECK_CLASSES for value in challenges):
        errors.append("review.challenge_classes: must be unique known classes")
        challenges = []
    if review.get("outcome") == "pass" and not set(plan["challenge_policy"]["required_classes"]).issubset(challenges):
        errors.append("review.challenge_classes: passing review must cover all required challenge classes")
    evidence = review.get("evidence_attestations")
    required_evidence = [check["attestation"] for check in plan["checks"] if check["critical"]]
    if evidence != required_evidence:
        errors.append("review.evidence_attestations: must equal ordered critical attestation paths")
    limitations = review.get("limitations")
    if not isinstance(limitations, list) or any(not isinstance(value, str) or not value.strip() for value in limitations):
        errors.append("review.limitations: must be a string list")
    if not isinstance(review.get("recorded_at"), str) or not review.get("recorded_at"):
        errors.append("review.recorded_at: must be a timestamp")
    return errors


def command_record_review(workflow_dir: Path, repo_root: Path, review_path: Path) -> dict[str, Any]:
    graph, plan, lock, _ = load_locked(workflow_dir, repo_root, "executable")
    evidence_errors = [
        error
        for check in plan["checks"] if check["critical"]
        for error in validate_attestation(workflow_dir, repo_root, check, lock["plan_digest"], lock["contract_digest"])
    ]
    if evidence_errors:
        raise ValueError("cannot review stale or failing evidence: " + "; ".join(evidence_errors))
    source = load_json(review_path, "review input")
    input_fields = {"schema_version", "verifier_node", "producer_nodes", "outcome", "challenge_classes", "evidence_attestations", "limitations"}
    if not isinstance(source, dict) or set(source) != input_fields:
        raise ValueError(f"review input must contain exactly {sorted(input_fields)!r}")
    review = {
        **source,
        "runner": RUNNER_ID,
        "runner_digest": runner_digest(),
        "plan_digest": lock["plan_digest"],
        "contract_digest": lock["contract_digest"],
        "recorded_at": now_utc(),
    }
    errors = validate_review(review, graph, plan, lock, workflow_dir)
    if errors:
        raise ValueError("; ".join(errors))
    destination_relative = f"integrity/reviews/{review['verifier_node']}.json"
    destination = resolve_under(workflow_dir, destination_relative)
    if destination.exists():
        existing = load_json(destination, "existing review")
        if existing != review:
            raise ValueError("review already exists; locked review records are append-resistant")
    else:
        atomic_json(destination, review)
    return {"verifier_node": review["verifier_node"], "outcome": review["outcome"], "review": destination_relative}


def command_validate(workflow_dir: Path, repo_root: Path, phase: str) -> dict[str, Any]:
    graph_phase = "complete" if phase == "complete" else "executable"
    graph, plan, lock, _ = load_locked(workflow_dir, repo_root, graph_phase)
    critical = [check for check in plan["checks"] if check["critical"]]
    evidence_errors = [
        error
        for check in critical
        for error in validate_attestation(workflow_dir, repo_root, check, lock["plan_digest"], lock["contract_digest"])
    ]
    if phase == "active":
        return {"phase": phase, "locked": True, "critical_checks": len(critical), "evidence_errors": evidence_errors}
    if evidence_errors:
        raise ValueError("; ".join(evidence_errors))
    reviews_dir = workflow_dir / "integrity" / "reviews"
    reviews = []
    review_errors: list[str] = []
    if reviews_dir.is_dir():
        for path in sorted(reviews_dir.glob("*.json")):
            value = load_json(path, f"review {path.name}")
            review_errors.extend(validate_review(value, graph, plan, lock, workflow_dir))
            if isinstance(value, dict) and value.get("outcome") == "pass":
                reviews.append(value)
    unique_verifiers = {review.get("verifier_node") for review in reviews}
    quorum = plan["separation_of_duties"]["min_independent_verifiers"]
    if len(unique_verifiers) < quorum:
        review_errors.append(f"review quorum: need {quorum}, found {len(unique_verifiers)}")
    claims = (graph.get("verification") or {}).get("claims", [])
    by_requirement: dict[str, set[str]] = {}
    for check in critical:
        for requirement in check["requirement_ids"]:
            by_requirement.setdefault(requirement, set()).add(check["attestation"])
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict) or claim.get("state") != "verified" or claim.get("requirement_id") is None:
            continue
        artifacts = {
            item.get("artifact")
            for item in claim.get("evidence", [])
            if isinstance(item, dict) and isinstance(item.get("artifact"), str)
        }
        if not artifacts & by_requirement.get(claim["requirement_id"], set()):
            review_errors.append(f"claim {claim.get('id')}: must cite a current critical runner attestation for its requirement")
    if review_errors:
        raise ValueError("; ".join(review_errors))
    return {"phase": phase, "locked": True, "critical_checks": len(critical), "passing_verifiers": sorted(unique_verifiers), "complete": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    lock = subparsers.add_parser("lock")
    lock.add_argument("workflow_dir", type=Path)
    lock.add_argument("--repo-root", type=Path, default=Path.cwd())
    validate = subparsers.add_parser("validate")
    validate.add_argument("workflow_dir", type=Path)
    validate.add_argument("--phase", choices=("active", "complete"), default="active")
    validate.add_argument("--repo-root", type=Path, default=Path.cwd())
    run = subparsers.add_parser("run")
    run.add_argument("workflow_dir", type=Path)
    run.add_argument("--check", required=True)
    run.add_argument("--repo-root", type=Path, default=Path.cwd())
    review = subparsers.add_parser("record-review")
    review.add_argument("workflow_dir", type=Path)
    review.add_argument("review", type=Path)
    review.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        workflow_dir = args.workflow_dir.resolve()
        repo_root = args.repo_root.resolve()
        if args.command == "lock":
            result = command_lock(workflow_dir, repo_root)
        elif args.command == "run":
            result = command_run(workflow_dir, repo_root, args.check)
        elif args.command == "record-review":
            result = command_record_review(workflow_dir, repo_root, args.review.resolve())
        else:
            result = command_validate(workflow_dir, repo_root, args.phase)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
