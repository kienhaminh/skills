#!/usr/bin/env python3
"""Run one digest-locked Graphflow node executor without a Goal trigger."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from executor_common import atomic_bytes, atomic_json, canonical_graph_digest, inside, load_executor, load_json, now_utc, sha256, validate_result
import progress_state
import workspace_manager


ROOT = Path(__file__).resolve().parent
EVIDENCE_RUNNER = ROOT / "evidence_runner.py"
CONTROL_PLANE_ROOTS = (
    "nodes",
    "integrity",
    "memory",
    "prototype",
    "dashboard",
    "evidence/attestations",
    "runtime/requests",
    "runtime/decompositions",
    "runtime/delivery",
    "runtime/scope",
)


def allowed_environment(names: list[str]) -> dict[str, str]:
    baseline = {name: os.environ[name] for name in ("PATH", "LANG", "LC_ALL", "TMPDIR") if name in os.environ}
    for name in names:
        if name in os.environ:
            baseline[name] = os.environ[name]
    return baseline


def check_authority(workflow_dir: Path, spec: dict[str, Any], node_id: str) -> None:
    runtime = load_json(workflow_dir / "runtime.json", "runtime authority")
    authority = runtime.get("authority") if isinstance(runtime, dict) and isinstance(runtime.get("authority"), dict) else {}
    grants = runtime.get("authority_grants") if isinstance(runtime, dict) and isinstance(runtime.get("authority_grants"), dict) else {}
    node_grant = grants.get(node_id) if isinstance(grants.get(node_id), dict) else {}
    node_capabilities = set(node_grant.get("capabilities", [])) if isinstance(node_grant.get("capabilities"), list) else set()
    missing = [
        capability for capability in spec.get("requires_authority", [])
        if authority.get(capability) is not True and capability not in node_capabilities
    ]
    if missing:
        raise ValueError(f"executor authority is missing: {', '.join(missing)}")


def control_plane_files(workflow_dir: Path, graph: dict[str, Any], spec: dict[str, Any]) -> set[Path]:
    paths = {
        workflow_dir / "graph.json",
        workflow_dir / "runtime.json",
        workflow_dir / "runtime" / "workspaces.json",
        workflow_dir / "runtime" / "checkout-baseline.json",
        workflow_dir / "runtime" / "checkout-status.json",
        workflow_dir / "runtime" / "checkout-events.jsonl",
        workflow_dir / "runtime" / "lease.json",
        workflow_dir / "memory" / "state.json",
        workflow_dir / "memory" / "events.jsonl",
        workflow_dir / "integrity" / "verification-plan.json",
        workflow_dir / "integrity" / "lock.json",
        workflow_dir / "runtime" / "progress" / f"{spec.get('node_id')}.json",
    }
    for resource in spec.get("resources", []):
        if isinstance(resource, dict) and isinstance(resource.get("path"), str):
            paths.add(inside(workflow_dir, resource["path"], "executor resource"))
    for path in (workflow_dir / "nodes").rglob("executor.json") if (workflow_dir / "nodes").is_dir() else []:
        paths.add(path.resolve())
    requests_dir = workflow_dir / "runtime" / "requests"
    if requests_dir.is_dir():
        paths.update(path.resolve() for path in requests_dir.glob("*.json") if path.is_file())
    decompositions_dir = workflow_dir / "runtime" / "decompositions"
    if decompositions_dir.is_dir():
        paths.update(path.resolve() for path in decompositions_dir.rglob("*") if path.is_file())
    intent = graph.get("intent_baseline") if isinstance(graph.get("intent_baseline"), dict) else {}
    manifest_value = intent.get("manifest")
    if isinstance(manifest_value, str):
        manifest_path = inside(workflow_dir, manifest_value, "intent manifest")
        paths.add(manifest_path)
        if manifest_path.is_file():
            manifest = load_json(manifest_path, "intent manifest")
            artifact = manifest.get("artifact") if isinstance(manifest, dict) else None
            if isinstance(artifact, str):
                paths.add(inside(workflow_dir, artifact, "intent artifact"))
    question_gate = graph.get("question_gate") if isinstance(graph.get("question_gate"), dict) else {}
    review_link = question_gate.get("review") if isinstance(question_gate.get("review"), dict) else {}
    if isinstance(review_link.get("artifact"), str):
        paths.add(inside(workflow_dir, review_link["artifact"], "question review"))
    evidence_dir = workflow_dir / "evidence" / "attestations"
    if evidence_dir.is_dir():
        paths.update(path.resolve() for path in evidence_dir.rglob("*") if path.is_file())
    return {path.resolve() for path in paths}


def directory_inventory(workflow_dir: Path, relative: str) -> dict[str, str]:
    root = workflow_dir / relative
    if not root.exists() and not root.is_symlink():
        return {}
    inventory: dict[str, str] = {".": "symlink" if root.is_symlink() else "directory" if root.is_dir() else "file"}
    if root.is_symlink() or not root.is_dir():
        return inventory
    for path in root.rglob("*"):
        item = path.relative_to(root).as_posix()
        inventory[item] = "symlink" if path.is_symlink() else "directory" if path.is_dir() else "file" if path.is_file() else "other"
    return inventory


def snapshot_control_plane(
    workflow_dir: Path, graph: dict[str, Any], spec: dict[str, Any],
) -> tuple[dict[Path, bytes | None], dict[str, dict[str, str]]]:
    inventories = {relative: directory_inventory(workflow_dir, relative) for relative in CONTROL_PLANE_ROOTS}
    for relative, inventory in inventories.items():
        symlinks = [item for item, kind in inventory.items() if kind == "symlink"]
        if symlinks:
            raise ValueError(f"control-plane symlink is not allowed under {relative}: {', '.join(symlinks)}")
    protected = control_plane_files(workflow_dir, graph, spec)
    for relative, inventory in inventories.items():
        root = workflow_dir / relative
        protected.update(root / item for item, kind in inventory.items() if item != "." and kind == "file")
    snapshot = {path: path.read_bytes() if path.is_file() else None for path in protected}
    return snapshot, inventories


def quarantine_destination(workflow_dir: Path, node_id: str, path: Path) -> Path:
    base = workflow_dir / "runtime" / "quarantine" / node_id / "control-plane" / path.relative_to(workflow_dir)
    destination = base
    suffix = 1
    while destination.exists() or destination.is_symlink():
        destination = base.with_name(f"{base.name}.{suffix}")
        suffix += 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def restore_control_plane(
    workflow_dir: Path, node_id: str, snapshot: dict[Path, bytes | None], inventories: dict[str, dict[str, str]],
) -> list[str]:
    changed: list[str] = []
    for relative, before in inventories.items():
        root = workflow_dir / relative
        current = directory_inventory(workflow_dir, relative)
        unexpected = sorted(set(current) - set(before), key=lambda item: (len(Path(item).parts), item))
        selected: list[str] = []
        for item in unexpected:
            if item == ".":
                selected = [item]
                break
            if any(parent == "." or Path(parent) in Path(item).parents for parent in selected):
                continue
            selected.append(item)
        for item in selected:
            path = root if item == "." else root / item
            if not path.exists() and not path.is_symlink():
                continue
            changed.append(str(path.relative_to(workflow_dir)))
            os.replace(path, quarantine_destination(workflow_dir, node_id, path))
        after_quarantine = directory_inventory(workflow_dir, relative)
        for item, kind in sorted(before.items(), key=lambda value: (len(Path(value[0]).parts), value[0])):
            if item in after_quarantine:
                continue
            path = root if item == "." else root / item
            if kind == "directory":
                path.mkdir(parents=True, exist_ok=True)
                changed.append(str(path.relative_to(workflow_dir)))
    for path, original in snapshot.items():
        current = path.read_bytes() if path.is_file() else None
        if current == original:
            continue
        changed.append(str(path.relative_to(workflow_dir)))
        if original is not None:
            atomic_bytes(path, original)
        elif path.is_file():
            os.replace(path, quarantine_destination(workflow_dir, node_id, path))
    return sorted(set(changed))


def declared_outputs(node: dict[str, Any], workflow_dir: Path, repo_root: Path) -> tuple[list[dict[str, str]], list[str]]:
    outputs: list[dict[str, str]] = []
    errors: list[str] = []
    for item in node.get("outputs", []):
        if not isinstance(item, dict) or not isinstance(item.get("artifact"), str):
            continue
        relative = item["artifact"]
        candidates = [(repo_root / relative).resolve(), (workflow_dir / relative).resolve()]
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            errors.append(f"declared output is missing: {relative}")
            continue
        outputs.append({"id": str(item.get("id")), "artifact": relative, "digest": sha256(path)})
    return outputs, errors


def run_acceptance(workflow_dir: Path, repo_root: Path, checks: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    evidence: list[dict[str, Any]] = []
    errors: list[str] = []
    for check_id in checks:
        completed = subprocess.run(
            [sys.executable, str(EVIDENCE_RUNNER), "run", str(workflow_dir), "--check", check_id, "--repo-root", str(repo_root)],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            outcome = json.loads(completed.stdout)
        except json.JSONDecodeError:
            outcome = None
        passed = completed.returncode == 0 and isinstance(outcome, dict) and outcome.get("passed") is True
        evidence.append({
            "kind": "acceptance",
            "check": check_id,
            "artifact": outcome.get("attestation") if isinstance(outcome, dict) else None,
            "digest": outcome.get("digest") if isinstance(outcome, dict) else None,
            "exit_code": completed.returncode,
            "note": None if passed else "Coordinator-run acceptance did not produce a passing attestation.",
        })
        if not passed:
            errors.append(f"acceptance check {check_id} failed: {(completed.stderr or completed.stdout).strip()}")
    return evidence, errors


def acceptance_checks(workflow_dir: Path, spec: dict[str, Any], workspace: dict[str, Any]) -> list[str]:
    if workspace.get("mode") != "verifier":
        return list(spec["acceptance_checks"])
    plan = load_json(workflow_dir / "integrity" / "verification-plan.json", "verification plan")
    checks = plan.get("checks") if isinstance(plan, dict) else None
    if not isinstance(checks, list):
        raise ValueError("verifier workspace requires a valid verification plan")
    critical = [item.get("id") for item in checks if isinstance(item, dict) and item.get("critical") is True]
    if not critical or any(not isinstance(item, str) for item in critical):
        raise ValueError("verifier workspace requires critical verification checks")
    return critical


def envelope(graph: dict[str, Any], node: dict[str, Any], spec: dict[str, Any], status: str, summary: str) -> dict[str, Any]:
    attempts = node.get("retry", {}).get("attempts", 0) if isinstance(node.get("retry"), dict) else 0
    return {
        "schema_version": 2,
        "workflow_id": graph.get("workflow_id"),
        "node_id": node.get("id"),
        "attempt": attempts,
        "idempotency_key": spec["idempotency_key"],
        "status": status,
        "summary": summary,
        "outputs": [],
        "evidence": [],
        "memory_delta": None,
        "request": None,
        "decomposition": None,
        "usage": {"input_tokens": None, "output_tokens": None},
    }


def run_command(graph: dict[str, Any], node: dict[str, Any], spec: dict[str, Any], cwd: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            spec["argv"], cwd=cwd, env=allowed_environment(spec.get("env_allow", [])),
            capture_output=True, text=True, timeout=spec["timeout_seconds"], check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return envelope(graph, node, spec, "failed", f"Command executor failed: {error}")
    status = "succeeded" if completed.returncode == 0 else "failed"
    result = envelope(graph, node, spec, status, f"Command exited with {completed.returncode}.")
    result["evidence"] = [{"kind": "command", "check": None, "artifact": None, "digest": None, "exit_code": completed.returncode, "note": None}]
    return result


def run_agent(
    graph: dict[str, Any], node: dict[str, Any], spec: dict[str, Any], workflow_dir: Path, cwd: Path,
    codex_bin: str, confirmation: dict[str, Any] | None,
) -> dict[str, Any]:
    prompt = inside(workflow_dir, spec["prompt"], "executor.prompt").read_text(encoding="utf-8")
    identity = envelope(graph, node, spec, "failed", "identity")
    inherited_bound = node.get("decomposition_bound")
    bound_instruction = (
        " If decomposing recursively, measure.name and measure.parent must equal this inherited bound exactly: "
        + json.dumps(inherited_bound, sort_keys=True)
        + "."
        if isinstance(inherited_bound, dict)
        else ""
    )
    prompt = (
        prompt.rstrip()
        + "\n\nReturn only JSON matching the supplied schema with this immutable identity:\n"
        + json.dumps({key: identity[key] for key in ("schema_version", "workflow_id", "node_id", "attempt", "idempotency_key")}, sort_keys=True)
        + f"\nCurrent semantic graph digest: {canonical_graph_digest(graph)}."
        + "\nApply Rumsfeld Matrix + Value of Information + Reversibility. Use an evidence-backed reversible default for local uncertainty. Ask only when material impact has no safe default and changes the node contract or graph baseline. If status is waiting_user or waiting_approval, include triage {blocking_scope, impacts, affected_nodes, no_safe_default_reason, resolution_mode, request_graph_digest, authority_capabilities}; use rebase for semantic impacts, copy the current graph digest exactly, include this node in affected_nodes, and compute request.digest as sha256 of compact sorted-key UTF-8 JSON containing exactly question, alternatives, risks, and triage. Otherwise request must be null. If the unchanged node contract is too complex to finish safely, status may be decompose with a structural-only MECE proposal: preserve objective/authority/oracle, make terminal_child acceptance and outputs byte-for-byte JSON-equal to this node's acceptance and outputs, exactly partition owned write/artifact/decision scopes, keep child budgets plus one coordination token within this node budget, use a strictly smaller positive complexity measure for every child, make every support child an ancestor of terminal_child, and apply Closed World Assumption so every child uses at least one existing locked acceptance check ID and their union equals this node's check set exactly."
        + bound_instruction
        + " Semantic decomposition must use waiting_user/waiting_approval instead. A decompose result must leave outputs/evidence empty and memory_delta/request null. Otherwise decomposition must be null. Do not edit graph, runtime, memory, integrity, executor resources, prototype baseline, or attestations."
    )
    if confirmation is not None:
        prompt += "\n\nDigest-bound confirmation response:\n" + json.dumps(confirmation, sort_keys=True)
    final_path = workflow_dir / "runtime" / "results" / f".{node['id']}.agent-final.json"
    events_path = workflow_dir / "runtime" / "agent-events" / f"{node['id']}.jsonl"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        codex_bin, "exec", "--json", "--output-schema", str(inside(workflow_dir, spec["result_schema"], "executor.result_schema")),
        "--output-last-message", str(final_path), "--cd", str(cwd), "--sandbox", spec["sandbox"],
        "--config", 'approval_policy="never"', "--ephemeral",
    ]
    if spec.get("model"):
        command.extend(["--model", spec["model"]])
    if spec.get("reasoning_effort"):
        command.extend(["--config", f"model_reasoning_effort={spec['reasoning_effort']}"])
    command.append("-")
    try:
        completed = subprocess.run(
            command, input=prompt, cwd=cwd, env=allowed_environment(spec.get("env_allow", [])),
            capture_output=True, text=True, timeout=spec["timeout_seconds"], check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return envelope(graph, node, spec, "failed", f"Agent executor failed: {error}")
    events_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0 or not final_path.is_file():
        return envelope(graph, node, spec, "failed", f"Agent executor exited with {completed.returncode} before a valid result.")
    result = load_json(final_path, "agent result")
    errors = validate_result(result, str(graph.get("workflow_id")), str(node.get("id")), int(identity["attempt"]), str(spec["idempotency_key"]))
    if errors:
        return envelope(graph, node, spec, "failed", "Invalid agent result: " + "; ".join(errors))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workflow_dir", type=Path)
    parser.add_argument("--node", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--codex-bin", default=shutil.which("codex") or "codex")
    parser.add_argument("--confirmation-file", type=Path)
    args = parser.parse_args()
    workflow_dir = args.workflow_dir.resolve()
    repo_root = args.repo_root.resolve()
    try:
        graph, node, spec, result_path = load_executor(workflow_dir, args.node)
        check_authority(workflow_dir, spec, str(node["id"]))
        cwd, workspace = workspace_manager.resolve(workflow_dir, repo_root, spec, str(node["id"]), provision=True)
        workspace_root = Path(str(workspace["path"])).resolve()
        progress_state.update(
            workflow_dir, str(node["id"]), "workspace_ready", workspace_ref=str(workspace["workspace_id"]),
            branch=workspace.get("branch"), head_sha=workspace.get("head_sha"),
        )
        scope_before = None
        if workspace.get("branch") != "(non-git)" and (node.get("scope", {}).get("write") or workspace.get("mode") != "primary"):
            scope_before = workspace_manager.snapshot(workspace_root)
        progress_state.update(
            workflow_dir, str(node["id"]), "running", heartbeat_at=now_utc(),
            workspace_ref=str(workspace["workspace_id"]), branch=workspace.get("branch"), head_sha=workspace.get("head_sha"),
        )
        protected, control_plane_inventories = snapshot_control_plane(workflow_dir, graph, spec)
        confirmation = load_json(args.confirmation_file.resolve(), "confirmation") if args.confirmation_file else None
        if spec["type"] == "command":
            result = run_command(graph, node, spec, cwd)
        else:
            result = run_agent(graph, node, spec, workflow_dir, cwd, args.codex_bin, confirmation)
        control_plane_changes = restore_control_plane(workflow_dir, args.node, protected, control_plane_inventories)
        if control_plane_changes:
            result = envelope(graph, node, spec, "failed", "Executor attempted control-plane mutation: " + ", ".join(control_plane_changes))
        scope_report = {"changed_files": [], "patch_digest": None, "manifest": []}
        if scope_before is not None:
            progress_state.update(workflow_dir, str(node["id"]), "scope_checking", workspace_ref=str(workspace["workspace_id"]))
            try:
                scope_report = workspace_manager.verify_scope(workspace_root, node, scope_before)
            except ValueError as error:
                result = envelope(graph, node, spec, "failed", f"Workspace scope verification failed: {error}")
            atomic_json(workflow_dir / "runtime" / "scope" / f"{node['id']}.json", scope_report)
            if result["status"] in {"decompose", "waiting_user", "waiting_approval", "waiting_external"} and scope_report["changed_files"]:
                result = envelope(
                    graph, node, spec, "failed",
                    "Executor changed its workspace before requesting a wait; partial changes require a new isolated attempt.",
                )
            if result["status"] == "succeeded":
                progress_state.update(
                    workflow_dir, str(node["id"]), "scope_accepted", workspace_ref=str(workspace["workspace_id"]),
                    branch=workspace.get("branch"), head_sha=workspace.get("head_sha"), changed_files=scope_report["changed_files"],
                )
        if result["status"] == "succeeded":
            running_phase = "verifier_running" if workspace.get("mode") == "verifier" else "evidence_running"
            progress_state.update(workflow_dir, str(node["id"]), running_phase, workspace_ref=str(workspace["workspace_id"]))
            outputs, output_errors = declared_outputs(node, workflow_dir, workspace_root)
            evidence, check_errors = run_acceptance(workflow_dir, workspace_root, acceptance_checks(workflow_dir, spec, workspace))
            result["outputs"] = outputs
            result["evidence"] = list(result.get("evidence", [])) + evidence
            if scope_before is not None:
                try:
                    final_scope = workspace_manager.verify_scope(workspace_root, node, scope_before)
                    if final_scope != scope_report:
                        atomic_json(workflow_dir / "runtime" / "scope" / f"{node['id']}.json", final_scope)
                        scope_report = final_scope
                except ValueError as error:
                    check_errors.append(f"post-acceptance scope verification failed: {error}")
            if output_errors or check_errors:
                result["status"] = "failed"
                result["summary"] = "; ".join(output_errors + check_errors)
            else:
                progress_state.update(workflow_dir, str(node["id"]), "evidence_passed", workspace_ref=str(workspace["workspace_id"]), changed_files=scope_report["changed_files"])
        errors = validate_result(
            result, str(graph.get("workflow_id")), str(node.get("id")),
            int(node.get("retry", {}).get("attempts", 0)), str(spec["idempotency_key"]),
        )
        if errors:
            raise ValueError("invalid final result: " + "; ".join(errors))
        result["completed_at"] = now_utc()
        result.pop("completed_at")  # schema remains exact; timestamp is recorded in runtime events
        atomic_json(result_path, result)
    except ValueError as error:
        try:
            progress_state.update(workflow_dir, args.node, "rejected", blocker=str(error))
        except ValueError:
            pass
        parser.error(str(error))
    print(json.dumps({"node": args.node, "result": str(result_path), "status": result["status"]}, sort_keys=True))
    return 0 if result["status"] in {"succeeded", "decompose", "waiting_user", "waiting_approval", "waiting_external"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
