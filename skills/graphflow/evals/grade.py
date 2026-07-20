#!/usr/bin/env python3
"""Deterministically grade one workflow-template eval artifact directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "workflow-template"
VALIDATOR = SKILL_ROOT / "scripts" / "validate_graph.py"
MEMORY = SKILL_ROOT / "scripts" / "memory_state.py"
INTEGRITY = SKILL_ROOT / "scripts" / "evidence_runner.py"
QUESTION_GATE = SKILL_ROOT / "scripts" / "question_gate.py"
EVALS = Path(__file__).resolve().with_name("evals.json")
DASHBOARD_FILES = ("index.html", "app.js", "styles.css")


def run(command: list[str]) -> tuple[int, str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def add_check(checks: list[dict[str, Any]], name: str, points: int, passed: bool, evidence: str) -> None:
    checks.append({"name": name, "points": points, "passed": passed, "evidence": evidence})


def grade(root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    graph_path = root / "graph.json"
    dashboard = root / "dashboard"
    result_path = root / "result.json"
    required = [
        graph_path,
        root / "runtime.json",
        root / "runtime" / "workspaces.json",
        root / "nodes" / "node-result.schema.json",
        root / "question-review.json",
        result_path,
        root / "memory" / "state.json",
        root / "memory" / "events.jsonl",
        root / "integrity" / "verification-plan.json",
        root / "integrity" / "lock.json",
        *(dashboard / name for name in DASHBOARD_FILES),
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    add_check(checks, "artifact contract", 1, not missing, "complete" if not missing else f"missing: {', '.join(missing)}")

    result = load_json(result_path) if result_path.is_file() else None
    graph = load_json(graph_path) if graph_path.is_file() else None
    definitions = load_json(EVALS)
    case_id = result.get("case_id") if isinstance(result, dict) else None
    cases = definitions.get("cases", []) if isinstance(definitions, dict) else []
    case = next((item for item in cases if isinstance(item, dict) and item.get("id") == case_id), None)
    phase = case.get("phase", "executable") if isinstance(case, dict) else "executable"
    case_constraints = case.get("constraints", {}) if isinstance(case, dict) and isinstance(case.get("constraints"), dict) else {}

    if graph_path.is_file():
        code, output = run([sys.executable, str(VALIDATOR), str(graph_path), "--phase", phase, "--ready"])
        add_check(checks, f"{phase} graph", 3, code == 0, output)
    else:
        add_check(checks, f"{phase} graph", 3, False, "graph.json missing")

    memory_phase = "complete" if phase == "complete" else "active"
    code, output = run([sys.executable, str(MEMORY), "--repo-root", str(root), "validate", str(root), "--phase", memory_phase, "--check-artifacts"])
    replay_code, replay_output = run([sys.executable, str(MEMORY), "replay", str(root), "--check"])
    add_check(checks, "shared memory", 2, code == 0 and replay_code == 0, f"validate={output}; replay={replay_output}")

    integrity_phase = "complete" if phase == "complete" else "active"
    integrity_repo = root
    code, output = run([sys.executable, str(INTEGRITY), "validate", str(root), "--phase", integrity_phase, "--repo-root", str(integrity_repo)])
    try:
        integrity_report = json.loads(output)
    except json.JSONDecodeError:
        integrity_report = None
    evidence_errors = integrity_report.get("evidence_errors", []) if isinstance(integrity_report, dict) else []
    active_errors_are_only_missing = integrity_phase == "active" and all(isinstance(item, str) and ": missing " in item for item in evidence_errors)
    integrity_ok = code == 0 and (not evidence_errors or active_errors_are_only_missing)
    add_check(checks, "proof-carrying integrity", 3, integrity_ok, output)

    app_path = dashboard / "app.js"
    node = shutil.which("node")
    if app_path.is_file() and node:
        code, output = run([node, "--check", str(app_path)])
        add_check(checks, "JavaScript syntax", 1, code == 0, output or "node --check passed")
    else:
        add_check(checks, "JavaScript syntax", 1, False, "app.js or node unavailable")

    dashboard_complete = all((dashboard / name).is_file() for name in DASHBOARD_FILES)
    if dashboard_complete:
        reused = all(digest(dashboard / name) == digest(TEMPLATE_ROOT / "dashboard" / name) for name in DASHBOARD_FILES)
        app_source = app_path.read_text(encoding="utf-8")
        html_source = (dashboard / "index.html").read_text(encoding="utf-8")
        css_source = (dashboard / "styles.css").read_text(encoding="utf-8")
        behavior = all(token in app_source for token in ("../graph.json", "../runtime.json", "../requests.json", "../progress.json", "../workspaces.json", "../checkout.json", "../memory/state.json", "setInterval", "visibilitychange", "textContent", "delivery.status", "decomposition.status", "checkout.status", "graph.intent_baseline", "graph.question_gate", "graph.integrity", "graph.verification"))
        unsafe = any(token in app_source for token in ("innerHTML", "outerHTML", "insertAdjacentHTML"))
        external = "https://" in html_source or "http://" in html_source or "@import url" in css_source
        add_check(checks, "template reuse", 1, reused, "dashboard files match bundled template" if reused else "dashboard diverged from template")
        add_check(checks, "live safe projection", 1, behavior and not unsafe and not external, f"behavior={behavior}, unsafe={unsafe}, external={external}")
    else:
        add_check(checks, "template reuse", 1, False, "dashboard files missing")
        add_check(checks, "live safe projection", 1, False, "dashboard files missing")

    server = result.get("server", {}) if isinstance(result, dict) else {}
    server_ok = (
        server.get("bind") == "127.0.0.1"
        and server.get("graph_http") == 200
        and server.get("runtime_http") == 200
        and server.get("requests_http") == 200
        and server.get("progress_http") == 200
        and server.get("workspaces_http") == 200
        and server.get("checkout_http") == 200
        and server.get("dashboard_http") == 200
        and server.get("memory_http") == 200
        and server.get("stopped") is True
        and isinstance(server.get("port"), int)
    )
    add_check(checks, "loopback hosting", 1, server_ok, json.dumps(server, sort_keys=True) if server else "result.json missing or invalid")

    adapted = (
        isinstance(graph, dict)
        and graph.get("workflow_id") != "publish-queue-bulk-retry"
        and digest(graph_path) != digest(TEMPLATE_ROOT / "graph.json")
    )
    add_check(checks, "task adaptation", 1, adapted, f"workflow_id={graph.get('workflow_id') if isinstance(graph, dict) else None}")

    executor_errors: list[str] = []
    executor_count = 0
    workspace_refs: set[str] = set()
    if isinstance(graph, dict):
        for node_spec in graph.get("nodes", []):
            if not isinstance(node_spec, dict) or node_spec.get("kind") == "expand":
                continue
            executor_count += 1
            node_id = node_spec.get("id")
            link = node_spec.get("executor")
            if not isinstance(link, dict):
                executor_errors.append(f"{node_id}: missing link")
                continue
            spec_value = link.get("spec")
            spec_path = root / spec_value if isinstance(spec_value, str) else None
            spec = load_json(spec_path) if spec_path and spec_path.is_file() else None
            expected = f"sha256:{digest(spec_path)}" if spec_path and spec_path.is_file() else None
            if not isinstance(spec, dict) or spec.get("node_id") != node_id or spec.get("type") != link.get("type"):
                executor_errors.append(f"{node_id}: invalid spec identity")
            workspace = spec.get("workspace") if isinstance(spec, dict) else None
            expected_mode = "verifier" if node_spec.get("kind") == "verify" else "integration" if node_spec.get("isolation") == "integration" else "worktree" if node_spec.get("isolation") == "worktree" else "primary"
            if not isinstance(spec, dict) or spec.get("schema_version") != 2 or not isinstance(workspace, dict) or set(workspace) != {"mode", "ref", "subdir"} or workspace.get("mode") != expected_mode:
                executor_errors.append(f"{node_id}: invalid v3 workspace contract")
            elif isinstance(workspace.get("ref"), str):
                workspace_refs.add(workspace["ref"])
            if expected != link.get("digest"):
                executor_errors.append(f"{node_id}: stale digest")
            if link.get("result") != f"runtime/results/{node_id}.json":
                executor_errors.append(f"{node_id}: invalid result path")
            if not isinstance(spec, dict) or not isinstance(spec.get("acceptance_checks"), list) or not spec.get("acceptance_checks"):
                executor_errors.append(f"{node_id}: missing acceptance checks")
            authority_requirements = spec.get("requires_authority") if isinstance(spec, dict) else None
            if not isinstance(authority_requirements, list) or any(not isinstance(item, str) for item in authority_requirements):
                executor_errors.append(f"{node_id}: invalid authority requirements")
            resources = spec.get("resources") if isinstance(spec, dict) else None
            if not isinstance(resources, list) or not resources:
                executor_errors.append(f"{node_id}: missing locked resources")
            else:
                for resource in resources:
                    resource_path = root / resource.get("path") if isinstance(resource, dict) and isinstance(resource.get("path"), str) else None
                    resource_digest = f"sha256:{digest(resource_path)}" if resource_path and resource_path.is_file() else None
                    if not isinstance(resource, dict) or resource.get("digest") != resource_digest:
                        executor_errors.append(f"{node_id}: stale resource digest")
            if isinstance(spec, dict) and spec.get("type") == "command" and (not isinstance(spec.get("argv"), list) or not spec.get("argv")):
                executor_errors.append(f"{node_id}: missing argv")
    workspace_registry = load_json(root / "runtime" / "workspaces.json")
    registry_entries = workspace_registry.get("entries") if isinstance(workspace_registry, dict) else None
    if not isinstance(registry_entries, dict) or workspace_registry.get("workflow_id") != (graph.get("workflow_id") if isinstance(graph, dict) else None):
        executor_errors.append("invalid workspace registry identity")
    else:
        if not workspace_refs.issubset(set(registry_entries)):
            executor_errors.append("executor workspace refs are missing from registry")
        allocations = [entry.get("allocations") for entry in registry_entries.values() if isinstance(entry, dict) and entry.get("mode") != "primary"]
        for field in ("slot", "port_offset", "database_suffix"):
            values = [item.get(field) for item in allocations if isinstance(item, dict)]
            if len(values) != len(set(map(str, values))) or any(value is None for value in values):
                executor_errors.append(f"workspace allocation collision or missing {field}")
    runtime = load_json(root / "runtime.json")
    runtime_authority = runtime.get("authority") if isinstance(runtime, dict) else None
    goal_independent = (
        isinstance(runtime, dict)
        and runtime.get("workflow_id") == (graph.get("workflow_id") if isinstance(graph, dict) else None)
        and runtime.get("goal_adapter") is None
        and isinstance(runtime_authority, dict)
        and all(isinstance(value, bool) for value in runtime_authority.values())
    )
    add_check(checks, "goal-independent executor contract", 3, executor_count > 0 and not executor_errors and goal_independent, f"executors={executor_count}, errors={executor_errors}, goal_optional={goal_independent}")
    decomposition = runtime.get("decomposition") if isinstance(runtime, dict) else None
    decomposition_ok = (
        isinstance(decomposition, dict)
        and decomposition.get("schema_version") == 1
        and decomposition.get("policy") == "structural-decomposition-v1"
        and decomposition.get("status") in {"idle", "reviewing", "waiting_rebase", "applied", "blocked"}
        and decomposition.get("reviewer_reasoning_effort") in {"low", "medium"}
        and isinstance(decomposition.get("revision"), int)
        and decomposition.get("revision") >= 0
    )
    add_check(checks, "runtime structural decomposition", 2, decomposition_ok, json.dumps(decomposition, sort_keys=True)[:600] if isinstance(decomposition, dict) else "missing")
    delivery = runtime.get("delivery") if isinstance(runtime, dict) else None
    delivery_ok = (
        isinstance(delivery, dict)
        and delivery.get("schema_version") == 1
        and delivery.get("adapter") == "ship-v1"
        and isinstance(delivery.get("required"), bool)
        and delivery.get("manifest") == "runtime/delivery/manifest.json"
        and delivery.get("proof") == "runtime/delivery/proof.json"
        and (
            (delivery.get("required") is False and delivery.get("status") == "not_required" and delivery.get("required_capabilities") == [])
            or (delivery.get("required") is True and delivery.get("status") in {"proposed", "waiting_approval", "publishing", "waiting_external", "published", "blocked"})
        )
    )
    add_check(checks, "Ship delivery contract", 2, delivery_ok, json.dumps(delivery, sort_keys=True)[:600] if isinstance(delivery, dict) else "missing")

    intent = graph.get("intent_baseline", {}) if isinstance(graph, dict) else {}
    prototype_ok = False
    prototype_evidence = "intent baseline missing"
    if isinstance(intent, dict) and intent.get("required") is False:
        prototype_ok = intent.get("status") == "not_required" and isinstance(intent.get("not_required_reason"), str) and bool(intent["not_required_reason"].strip())
        prototype_evidence = f"deterministic exemption={prototype_ok}"
    elif isinstance(intent, dict) and intent.get("required") is True:
        manifest_value = intent.get("manifest")
        manifest_path = root / manifest_value if isinstance(manifest_value, str) else None
        manifest = load_json(manifest_path) if manifest_path and manifest_path.is_file() else None
        artifact_value = manifest.get("artifact") if isinstance(manifest, dict) else None
        artifact_path = root / artifact_value if isinstance(artifact_value, str) else None
        actual_digest = f"sha256:{digest(artifact_path)}" if artifact_path and artifact_path.is_file() else None
        prototype_ok = (
            intent.get("status") == "approved"
            and intent.get("approval") in {"user", "deterministic"}
            and (manifest.get("workflow_id") if isinstance(manifest, dict) else None) == graph.get("workflow_id")
            and actual_digest == intent.get("digest") == (manifest.get("baseline_digest") if isinstance(manifest, dict) else None)
        )
        prototype_evidence = f"manifest={bool(manifest)}, artifact={bool(artifact_path and artifact_path.is_file())}, digest_match={actual_digest == intent.get('digest')}"
    add_check(checks, "prototype gate", 2, prototype_ok, prototype_evidence)

    question_gate = graph.get("question_gate", {}) if isinstance(graph, dict) else {}
    question_code, question_output = run([sys.executable, str(QUESTION_GATE), "validate", str(root)])
    question_ok = (
        isinstance(question_gate, dict)
        and question_gate.get("methods") == ["Rumsfeld Matrix", "Value of Information", "Reversibility"]
        and question_gate.get("status") == "clear"
        and question_gate.get("unresolved_pivotal") == []
        and isinstance(question_gate.get("review"), dict)
        and question_gate["review"].get("status") == "locked"
        and question_code == 0
    )
    add_check(checks, "question triage gate", 2, question_ok, question_output or (json.dumps(question_gate, sort_keys=True) if isinstance(question_gate, dict) else "missing"))

    verification = graph.get("verification", {}) if isinstance(graph, dict) else {}
    verification_ok = isinstance(verification, dict) and verification.get("outcome") in {"pending", "verified", "complete_with_limits"} and isinstance(verification.get("claims"), list)
    if phase == "complete":
        verification_ok = verification_ok and verification.get("outcome") in {"verified", "complete_with_limits"} and bool(verification.get("claims"))
    add_check(checks, "calibrated evidence contract", 1, verification_ok, json.dumps(verification, sort_keys=True)[:500] if isinstance(verification, dict) else "missing")
    result_ready = result.get("ready_frontier") if isinstance(result, dict) else None
    ready_ok = isinstance(result_ready, list) and (not result_ready if phase == "complete" else bool(result_ready))
    budget_ok = False
    if isinstance(graph, dict):
        constraints = graph.get("constraints")
        budget = constraints.get("token_budget") if isinstance(constraints, dict) else None
        budget_ok = isinstance(budget, int) and budget > 0
    add_check(checks, "operational handoff", 1, ready_ok and budget_ok and result.get("used_template") is True if isinstance(result, dict) else False, f"ready={result_ready}, budget_declared={budget_ok}")

    constraints = case_constraints
    if isinstance(constraints, dict) and constraints.get("requires_shared_memory_handoff") is True:
        memory = load_json(root / "memory" / "state.json")
        entries = memory.get("entries", []) if isinstance(memory, dict) else []
        capsules = sorted((root / "memory" / "capsules").glob("*.json")) if (root / "memory" / "capsules").is_dir() else []
        capsule_values = [load_json(path) for path in capsules]
        capsules_current = bool(capsules) and all(
            isinstance(value, dict)
            and value.get("memory_revision") == memory.get("revision")
            and value.get("graph_digest") == memory.get("graph_digest")
            for value in capsule_values
        ) if isinstance(memory, dict) else False
        try:
            event_count = len([line for line in (root / "memory" / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()])
        except OSError:
            event_count = 0
        handoff_ok = len(entries) >= 2 and len(capsules) >= 2 and capsules_current and event_count >= 3
        add_check(checks, "selective shared-memory handoff", 2, handoff_ok, f"entries={len(entries)}, capsules={len(capsules)}, current={capsules_current}, events={event_count}")

    if isinstance(constraints, dict) and constraints.get("requires_adversarial_integrity") is True:
        attack_paths = [
            root / "checks" / "fake-attestation.stderr",
            root / "checks" / "weakened-plan.stderr",
            root / "checks" / "producer-verified.stderr",
        ]
        attack_text = []
        for path in attack_paths:
            try:
                attack_text.append(path.read_text(encoding="utf-8").strip())
            except OSError:
                attack_text.append("")
        attacks_ok = all(attack_text) and all("ERROR" in value or "error" in value.lower() or "reject" in value.lower() for value in attack_text)
        add_check(checks, "adversarial integrity rejection", 3, attacks_ok, f"captured={sum(bool(value) for value in attack_text)}/3")

    if isinstance(constraints, dict) and constraints.get("requires_goal_independent_execution") is True:
        try:
            runtime_events = (root / "runtime" / "events.jsonl").read_text(encoding="utf-8")
        except OSError:
            runtime_events = ""
        node_results = [load_json(path) for path in sorted((root / "runtime" / "results").glob("*.json"))] if (root / "runtime" / "results").is_dir() else []
        executed = (
            '"type":"runner_started"' in runtime_events
            and '"type":"node_dispatched"' in runtime_events
            and '"type":"node_finished"' in runtime_events
            and any(isinstance(item, dict) and item.get("status") == "succeeded" for item in node_results)
            and isinstance(runtime, dict)
            and runtime.get("goal_adapter") is None
        )
        add_check(checks, "Goal-independent execution trace", 4, executed, f"events={len(runtime_events.splitlines())}, succeeded_results={sum(isinstance(item, dict) and item.get('status') == 'succeeded' for item in node_results)}")

    extra_required = case.get("required_artifacts", []) if isinstance(case, dict) else []
    if extra_required:
        missing_extra = [name for name in extra_required if not (root / name).is_file()]
        machine = load_json(root / "machine-profile.json")
        repository = load_json(root / "repo-profile.json")
        options = load_json(root / "cost-options.json")
        review = load_json(root / "cost-review.json")
        sanitization = machine.get("sanitization", {}) if isinstance(machine, dict) else {}
        sanitized = all(sanitization.get(field) == "excluded" for field in ("environment_values", "credentials", "process_arguments", "hardware_serials", "arbitrary_user_files"))
        option_values = options.get("options", []) if isinstance(options, dict) else []
        option_ids = {item.get("id") for item in option_values if isinstance(item, dict)}
        reviewed = isinstance(review, dict) and review.get("selected") == "balanced" and review.get("assessment") in {"proportionate", "user-confirmed"}
        detached_activation = (
            isinstance(graph, dict)
            and graph.get("version") == 3
            and "goal_binding" not in graph
            and isinstance(graph.get("lifecycle"), dict)
            and "execution_policy" not in graph
            and isinstance(graph.get("optional_work"), list)
        )
        lifecycle_ok = not missing_extra and isinstance(repository, dict) and sanitized and {"economy", "balanced", "deep"}.issubset(option_ids) and reviewed and detached_activation
        evidence = f"missing={missing_extra}, sanitized={sanitized}, options={sorted(option_ids)}, reviewed={reviewed}, detached_activation={detached_activation}"
        add_check(checks, "detached activation lifecycle", 2, lifecycle_ok, evidence)

    score = sum(check["points"] for check in checks if check["passed"])
    maximum = sum(check["points"] for check in checks)
    critical = {
        "artifact contract",
        f"{phase} graph",
        "shared memory",
        "proof-carrying integrity",
        "live safe projection",
        "loopback hosting",
        "task adaptation",
        "prototype gate",
        "question triage gate",
        "calibrated evidence contract",
        "operational handoff",
        "goal-independent executor contract",
        "runtime structural decomposition",
        "Ship delivery contract",
    }
    if isinstance(constraints, dict) and constraints.get("requires_shared_memory_handoff") is True:
        critical.add("selective shared-memory handoff")
    if isinstance(constraints, dict) and constraints.get("requires_adversarial_integrity") is True:
        critical.add("adversarial integrity rejection")
    if isinstance(constraints, dict) and constraints.get("requires_goal_independent_execution") is True:
        critical.add("Goal-independent execution trace")
    critical_passed = all(check["passed"] for check in checks if check["name"] in critical) and critical.issubset({check["name"] for check in checks})
    return {"score": score, "maximum": maximum, "passed": score >= math.ceil(maximum * 0.8) and critical_passed, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    report = grade(args.artifact_dir.resolve())
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"SCORE {report['score']}/{report['maximum']} {'PASS' if report['passed'] else 'FAIL'}")
        for check in report["checks"]:
            marker = "PASS" if check["passed"] else "FAIL"
            print(f"{marker} {check['name']} ({check['points']}): {check['evidence']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
