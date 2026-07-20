#!/usr/bin/env python3
"""Regression tests for independent preflight question review locking."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "workflow-template"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("graphflow_question_gate", ROOT / "scripts" / "question_gate.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
from skills.graphflow.evals.fixture_support import complete_clear_review


class QuestionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workflow = Path(self.temporary.name) / "workflow"
        shutil.copytree(TEMPLATE, self.workflow)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def prepare_review(self) -> tuple[dict, dict]:
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["question_gate"]["review"] = {
            "status": "required", "artifact": "question-review.json", "digest": None,
            "graph_digest": None, "reviewer_id": None,
        }
        review_path = self.workflow / "question-review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        complete_clear_review(review)
        review["graph_digest"] = GATE.question_surface_digest(graph)
        review["reviewer"]["agent_id"] = "fresh-test-challenger"
        review["reviewed_at"] = "2026-07-20T00:00:00Z"
        self.write(graph_path, graph)
        self.write(review_path, review)
        return graph, review

    def test_locked_review_is_current_and_semantic_drift_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "locked|digest"):
            GATE.validate(self.workflow)
        self.prepare_review()
        self.assertTrue(GATE.lock(self.workflow)["locked"])
        self.assertTrue(GATE.validate(self.workflow)["valid"])
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["objective"]["statement"] += " Changed."
        self.write(graph_path, graph)
        with self.assertRaisesRegex(ValueError, "stale|does not match"):
            GATE.validate(self.workflow)
        self.prepare_review()
        self.assertTrue(GATE.lock(self.workflow)["locked"])
        self.assertTrue(GATE.validate(self.workflow)["valid"])

    def test_review_requires_all_premortem_challenges(self) -> None:
        _, review = self.prepare_review()
        review["challenges"] = review["challenges"][:-1]
        self.write(self.workflow / "question-review.json", review)
        with self.assertRaisesRegex(ValueError, "cover exactly"):
            GATE.lock(self.workflow)

    def test_open_pivotal_findings_must_match_graph_gate(self) -> None:
        graph, review = self.prepare_review()
        finding = {
            "id": "Q1",
            "question": "Which public contract is authoritative?",
            "impacts": ["scope", "intent_baseline"],
            "disposition": "pivotal_open",
            "rationale": "Both repository routes are currently live.",
            "evidence": ["route inventory"],
        }
        review["findings"] = [finding]
        review["status"] = "open"
        graph["question_gate"]["status"] = "open"
        graph["question_gate"]["unresolved_pivotal"] = [
            {"id": "Q1", "question": finding["question"], "impacts": finding["impacts"]}
        ]
        review["graph_digest"] = GATE.question_surface_digest(graph)
        self.write(self.workflow / "graph.json", graph)
        self.write(self.workflow / "question-review.json", review)
        self.assertEqual(GATE.lock(self.workflow)["status"], "open")


if __name__ == "__main__":
    unittest.main()
