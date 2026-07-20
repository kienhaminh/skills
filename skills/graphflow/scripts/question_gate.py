#!/usr/bin/env python3
"""Lock and validate an independent Graphflow question-challenge review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from executor_common import DIGEST_RE, QUESTION_IMPACTS, atomic_json, load_json, question_surface_digest, sha256


METHODS = ["Rumsfeld Matrix", "Value of Information", "Reversibility", "Premortem"]
CHALLENGE_CLASSES = {"misread-intent", "hidden-dependency", "oracle-gap"}
DISPOSITIONS = {"resolved", "reversible_default", "optional", "pivotal_open"}


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_review(review: Any, graph: dict[str, Any], *, expected_graph_digest: str | None = None) -> list[str]:
    errors: list[str] = []
    fields = {"schema_version", "workflow_id", "graph_digest", "methods", "reviewer", "challenges", "findings", "status", "reviewed_at"}
    if not isinstance(review, dict) or set(review) != fields:
        return [f"review must contain exactly {sorted(fields)!r}"]
    if review.get("schema_version") != 1:
        errors.append("review.schema_version must equal 1")
    if review.get("workflow_id") != graph.get("workflow_id"):
        errors.append("review.workflow_id must match graph")
    if review.get("graph_digest") != (expected_graph_digest or question_surface_digest(graph)):
        errors.append("review.graph_digest does not match the current question surface")
    if review.get("methods") != METHODS:
        errors.append(f"review.methods must equal {METHODS!r}")
    reviewer = review.get("reviewer")
    reviewer_fields = {"agent_id", "model_class", "model_id", "independent", "context_policy"}
    if not isinstance(reviewer, dict) or set(reviewer) != reviewer_fields:
        errors.append(f"review.reviewer must contain exactly {sorted(reviewer_fields)!r}")
    else:
        if not nonempty(reviewer.get("agent_id")):
            errors.append("review.reviewer.agent_id must be non-empty")
        if reviewer.get("model_class") not in {"small", "frontier"}:
            errors.append("review.reviewer.model_class must be small or frontier")
        if reviewer.get("model_id") is not None and not nonempty(reviewer.get("model_id")):
            errors.append("review.reviewer.model_id must be null or non-empty")
        if reviewer.get("independent") is not True:
            errors.append("review.reviewer.independent must be true")
        if reviewer.get("context_policy") != "fresh-artifacts-only":
            errors.append("review.reviewer.context_policy must be fresh-artifacts-only")
    challenges = review.get("challenges")
    seen_classes: set[str] = set()
    if not isinstance(challenges, list):
        errors.append("review.challenges must be a list")
    else:
        for index, challenge in enumerate(challenges):
            if not isinstance(challenge, dict) or set(challenge) != {"class", "result", "rationale"}:
                errors.append(f"review.challenges[{index}] must contain exactly class, result, and rationale")
                continue
            challenge_class = challenge.get("class")
            if challenge_class not in CHALLENGE_CLASSES or challenge_class in seen_classes:
                errors.append(f"review.challenges[{index}].class must be a unique required challenge class")
            else:
                seen_classes.add(challenge_class)
            if challenge.get("result") not in {"clear", "finding"}:
                errors.append(f"review.challenges[{index}].result must be clear or finding")
            if not nonempty(challenge.get("rationale")):
                errors.append(f"review.challenges[{index}].rationale must be non-empty")
        if seen_classes != CHALLENGE_CLASSES:
            errors.append(f"review.challenges must cover exactly {sorted(CHALLENGE_CLASSES)!r}")
    findings = review.get("findings")
    pivotal: list[dict[str, Any]] = []
    finding_ids: set[str] = set()
    if not isinstance(findings, list):
        errors.append("review.findings must be a list")
    else:
        for index, finding in enumerate(findings):
            fields = {"id", "question", "impacts", "disposition", "rationale", "evidence"}
            if not isinstance(finding, dict) or set(finding) != fields:
                errors.append(f"review.findings[{index}] must contain exactly {sorted(fields)!r}")
                continue
            finding_id = finding.get("id")
            if not nonempty(finding_id) or finding_id in finding_ids:
                errors.append(f"review.findings[{index}].id must be unique and non-empty")
            else:
                finding_ids.add(finding_id)
            if not nonempty(finding.get("question")) or not nonempty(finding.get("rationale")):
                errors.append(f"review.findings[{index}] requires question and rationale")
            impacts = finding.get("impacts")
            if not isinstance(impacts, list) or not impacts or len(impacts) != len(set(impacts)) or any(value not in QUESTION_IMPACTS for value in impacts):
                errors.append(f"review.findings[{index}].impacts must be a unique controlled non-empty list")
            disposition = finding.get("disposition")
            if disposition not in DISPOSITIONS:
                errors.append(f"review.findings[{index}].disposition is invalid")
            evidence = finding.get("evidence")
            if not isinstance(evidence, list) or any(not nonempty(value) for value in evidence):
                errors.append(f"review.findings[{index}].evidence must be a string list")
            if disposition == "reversible_default" and not evidence:
                errors.append(f"review.findings[{index}] reversible_default requires evidence")
            if disposition == "pivotal_open":
                pivotal.append({"id": finding_id, "question": finding.get("question"), "impacts": impacts})
    expected_status = "open" if pivotal else "passed"
    if review.get("status") != expected_status:
        errors.append(f"review.status must be {expected_status}")
    if not nonempty(review.get("reviewed_at")):
        errors.append("review.reviewed_at must be non-empty")
    gate = graph.get("question_gate") if isinstance(graph.get("question_gate"), dict) else {}
    expected_gate_status = "open" if pivotal else "clear"
    if gate.get("status") != expected_gate_status or gate.get("unresolved_pivotal") != pivotal:
        errors.append("graph question_gate status/unresolved_pivotal must exactly match the independent review")
    return errors


def load_contract(workflow_dir: Path) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    graph_path = workflow_dir / "graph.json"
    graph = load_json(graph_path, "graph")
    if not isinstance(graph, dict) or graph.get("version") != 3:
        raise ValueError("question review requires a Graphflow v3 graph")
    gate = graph.get("question_gate") if isinstance(graph.get("question_gate"), dict) else {}
    link = gate.get("review") if isinstance(gate.get("review"), dict) else {}
    artifact = link.get("artifact")
    if not isinstance(artifact, str) or not artifact or Path(artifact).is_absolute() or ".." in Path(artifact).parts:
        raise ValueError("question_gate.review.artifact must be a safe relative path")
    review_path = workflow_dir / artifact
    review = load_json(review_path, "question review")
    return graph_path, graph, review_path, review


def lock(workflow_dir: Path) -> dict[str, Any]:
    graph_path, graph, review_path, review = load_contract(workflow_dir)
    errors = validate_review(review, graph)
    if errors:
        raise ValueError("; ".join(errors))
    reviewer = review["reviewer"]
    graph["question_gate"]["review"] = {
        "status": "locked",
        "artifact": str(review_path.relative_to(workflow_dir)),
        "digest": sha256(review_path),
        "graph_digest": question_surface_digest(graph),
        "reviewer_id": reviewer["agent_id"],
    }
    atomic_json(graph_path, graph)
    return {"locked": True, "status": graph["question_gate"]["status"], "review_digest": sha256(review_path)}


def validate(workflow_dir: Path) -> dict[str, Any]:
    _, graph, review_path, review = load_contract(workflow_dir)
    errors = validate_review(review, graph)
    link = graph.get("question_gate", {}).get("review", {})
    if link.get("status") != "locked":
        errors.append("question_gate.review.status must be locked")
    if link.get("digest") != sha256(review_path):
        errors.append("question_gate.review.digest does not match the review artifact")
    if link.get("graph_digest") != question_surface_digest(graph):
        errors.append("question_gate.review.graph_digest is stale")
    reviewer = review.get("reviewer") if isinstance(review, dict) else None
    if not isinstance(reviewer, dict) or link.get("reviewer_id") != reviewer.get("agent_id"):
        errors.append("question_gate.review.reviewer_id does not match the artifact")
    if errors:
        raise ValueError("; ".join(errors))
    return {"valid": True, "status": graph["question_gate"]["status"], "review_digest": link["digest"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("surface", "lock", "validate"))
    parser.add_argument("workflow_dir", type=Path)
    args = parser.parse_args()
    try:
        workflow_dir = args.workflow_dir.resolve()
        if args.command == "surface":
            graph = load_json(workflow_dir / "graph.json", "graph")
            if not isinstance(graph, dict):
                raise ValueError("graph must be an object")
            result = {"workflow_id": graph.get("workflow_id"), "graph_digest": question_surface_digest(graph)}
        else:
            result = lock(workflow_dir) if args.command == "lock" else validate(workflow_dir)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
