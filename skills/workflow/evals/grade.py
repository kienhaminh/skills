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
    required = [graph_path, result_path, root / "memory" / "state.json", root / "memory" / "events.jsonl", *(dashboard / name for name in DASHBOARD_FILES)]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    add_check(checks, "artifact contract", 1, not missing, "complete" if not missing else f"missing: {', '.join(missing)}")

    result = load_json(result_path) if result_path.is_file() else None
    graph = load_json(graph_path) if graph_path.is_file() else None
    definitions = load_json(EVALS)
    case_id = result.get("case_id") if isinstance(result, dict) else None
    cases = definitions.get("cases", []) if isinstance(definitions, dict) else []
    case = next((item for item in cases if isinstance(item, dict) and item.get("id") == case_id), None)
    phase = case.get("phase", "executable") if isinstance(case, dict) else "executable"

    if graph_path.is_file():
        code, output = run([sys.executable, str(VALIDATOR), str(graph_path), "--phase", phase, "--ready"])
        add_check(checks, f"{phase} graph", 3, code == 0, output)
    else:
        add_check(checks, f"{phase} graph", 3, False, "graph.json missing")

    memory_phase = "complete" if phase == "complete" else "active"
    code, output = run([sys.executable, str(MEMORY), "validate", str(root), "--phase", memory_phase, "--check-artifacts"])
    replay_code, replay_output = run([sys.executable, str(MEMORY), "replay", str(root), "--check"])
    add_check(checks, "shared memory", 2, code == 0 and replay_code == 0, f"validate={output}; replay={replay_output}")

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
        behavior = all(token in app_source for token in ("../graph.json", "../memory/state.json", "setInterval", "visibilitychange", "textContent", "graph.intent_baseline", "graph.verification"))
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

    constraints = case.get("constraints", {}) if isinstance(case, dict) else {}
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
            and graph.get("version") == 1
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
        "live safe projection",
        "loopback hosting",
        "task adaptation",
        "prototype gate",
        "calibrated evidence contract",
        "operational handoff",
    }
    if isinstance(constraints, dict) and constraints.get("requires_shared_memory_handoff") is True:
        critical.add("selective shared-memory handoff")
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
