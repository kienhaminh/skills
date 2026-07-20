"""Make the neutral public template executable inside isolated test fixtures."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import evidence_runner  # noqa: E402
import question_gate  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def complete_clear_review(review: dict) -> dict:
    """Replace template placeholders with explicit fresh-test review outcomes."""
    rationales = {
        "misread-intent": "The test objective and acceptance contract agree.",
        "hidden-dependency": "The test dependency graph has no hidden handoff.",
        "oracle-gap": "The test verification plan covers every required claim.",
    }
    for challenge in review["challenges"]:
        challenge.update(result="clear", rationale=rationales[challenge["class"]])
    review["status"] = "passed"
    return review


def approve_manifest(workflow: Path, graph: dict, approval: str = "user") -> None:
    """Bind a test graph to the current baseline artifact and approved manifest."""
    manifest_path = workflow / graph["intent_baseline"]["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(status="approved", approval=approval)
    write_json(manifest_path, manifest)
    graph["intent_baseline"].update(
        status="approved",
        digest="sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        approval=approval,
    )


def approve_intent_and_review(workflow: Path) -> None:
    """Supply fresh intent approval and independent review for a test workflow."""
    graph_path = workflow / "graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    approve_manifest(workflow, graph)
    next(node for node in graph["nodes"] if node["id"] == "P")["status"] = "complete"
    write_json(graph_path, graph)

    review_path = workflow / "question-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    complete_clear_review(review)
    review["graph_digest"] = question_gate.question_surface_digest(graph)
    review["reviewed_at"] = "2026-07-20T00:00:00Z"
    write_json(review_path, review)
    question_gate.lock(workflow)


def approve_template_for_execution(workflow: Path, repo: Path) -> None:
    """Supply every execution precondition for a disposable test workflow."""
    approve_intent_and_review(workflow)
    evidence_runner.command_lock(workflow, repo)
