#!/usr/bin/env python3
"""Regression tests for workflow safety gates."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "workflow-template" / "graph.json"
SPEC = importlib.util.spec_from_file_location("workflow_validator", ROOT / "scripts" / "validate_graph.py")
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def graph() -> dict:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def errors(data: dict, phase: str = "executable") -> list[str]:
    return VALIDATOR.validate(data, phase)[0]


def complete_graph() -> dict:
    data = graph()
    data["lifecycle"]["status"] = "complete"
    for node in data["nodes"]:
        if node["kind"] != "expand":
            node["status"] = "complete"
    data["verification"] = {
        "outcome": "verified",
        "claims": [
            {
                "id": f"C-{requirement['id']}",
                "requirement_id": requirement["id"],
                "statement": requirement["text"],
                "state": "verified",
                "confidence": "high",
                "evidence": [{"check": f"check {requirement['id']}", "artifact": f"evidence/{requirement['id'].lower()}.json"}],
                "limitations": [],
            }
            for requirement in data["objective"]["requirements"]
        ],
    }
    return data


class ValidatorSafetyTests(unittest.TestCase):
    def test_template_is_executable(self) -> None:
        self.assertEqual(errors(graph()), [])

    def test_missing_or_unapproved_intent_fails(self) -> None:
        missing = graph()
        del missing["intent_baseline"]
        self.assertTrue(any("intent_baseline" in item for item in errors(missing)))

        proposed = graph()
        proposed["intent_baseline"].update(status="proposed", digest=None, approval=None)
        self.assertTrue(any("approved" in item for item in errors(proposed)))

    def test_broad_work_must_descend_from_prototype(self) -> None:
        data = graph()
        next(node for node in data["nodes"] if node["id"] == "B")["depends_on"] = []
        self.assertTrue(any("approved prototype" in item for item in errors(data)))

    def test_deterministic_exemption_is_executable(self) -> None:
        data = graph()
        data["intent_baseline"] = {
            "required": False,
            "status": "not_required",
            "manifest": None,
            "digest": None,
            "approval": None,
            "not_required_reason": "Exact characterization test defines the mechanical rename.",
        }
        data["nodes"] = [node for node in data["nodes"] if node["id"] != "P"]
        next(node for node in data["nodes"] if node["id"] == "B")["depends_on"] = []
        self.assertEqual(errors(data), [])

    def test_method_primary_is_semantic(self) -> None:
        data = graph()
        next(node for node in data["nodes"] if node["id"] == "D")["methods"][0] = "MECE"
        self.assertTrue(any("primary method" in item for item in errors(data)))

    def test_shared_memory_contract_and_reservation(self) -> None:
        missing = graph()
        del missing["shared_memory"]
        self.assertTrue(any("shared_memory" in item for item in errors(missing)))

        claimed = graph()
        next(node for node in claimed["nodes"] if node["id"] == "D")["scope"]["artifacts"] = ["memory/capsules/D.json"]
        self.assertTrue(any("coordinator-reserved shared memory" in item for item in errors(claimed)))

    def test_complete_requires_direct_primary_claims(self) -> None:
        data = graph()
        data["lifecycle"]["status"] = "complete"
        for node in data["nodes"]:
            if node["kind"] != "expand":
                node["status"] = "complete"
        self.assertTrue(any("primary claim" in item for item in errors(data, "complete")))

    def test_verified_completion_and_limited_extras(self) -> None:
        verified = complete_graph()
        self.assertEqual(errors(verified, "complete"), [])

        limited = copy.deepcopy(verified)
        limited["verification"]["outcome"] = "complete_with_limits"
        limited["verification"]["claims"].append(
            {
                "id": "C-OPTIONAL",
                "requirement_id": None,
                "statement": "Large-fixture performance is acceptable.",
                "state": "unverified",
                "confidence": "none",
                "evidence": [],
                "limitations": ["Large disposable fixture was unavailable."],
            }
        )
        self.assertEqual(errors(limited, "complete"), [])

    def test_primary_inference_and_unowned_evidence_fail(self) -> None:
        inferred = complete_graph()
        inferred["verification"]["claims"][0].update(state="inferred", confidence="low", evidence=[])
        self.assertTrue(any("required claim R1" in item for item in errors(inferred, "complete")))

        unowned = complete_graph()
        unowned["verification"]["claims"][0]["evidence"][0]["artifact"] = "outside/evidence.json"
        self.assertTrue(any("must be owned by a verify node" in item for item in errors(unowned, "complete")))


if __name__ == "__main__":
    unittest.main()
