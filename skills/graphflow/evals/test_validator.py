#!/usr/bin/env python3
"""Regression tests for workflow safety gates."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "workflow-template" / "graph.json"
SPEC = importlib.util.spec_from_file_location("workflow_validator", ROOT / "scripts" / "validate_graph.py")
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def graph() -> dict:
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    manifest = json.loads((TEMPLATE.parent / "prototype/manifest.json").read_text(encoding="utf-8"))
    manifest.update(status="approved", approval="user")
    manifest_digest = "sha256:" + hashlib.sha256(
        (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    ).hexdigest()
    data["integrity"].update(
        status="locked",
        plan_digest="sha256:" + "1" * 64,
        runner_digest="sha256:" + "2" * 64,
    )
    data["question_gate"]["review"].update(
        status="locked",
        digest="sha256:" + "3" * 64,
        graph_digest="sha256:" + "4" * 64,
        reviewer_id="independent-reviewer",
    )
    data["intent_baseline"].update(
        status="approved",
        digest=manifest_digest,
        approval="user",
    )
    next(node for node in data["nodes"] if node["id"] == "P")["status"] = "complete"
    return data


def errors(
    data: dict,
    phase: str = "executable",
    mutate_manifest: Callable[[dict], None] | None = None,
    mutate_artifact: Callable[[Path], None] | None = None,
) -> list[str]:
    with tempfile.TemporaryDirectory() as temporary:
        workflow = Path(temporary) / "workflow"
        shutil.copytree(TEMPLATE.parent, workflow)
        intent = data.get("intent_baseline")
        if isinstance(intent, dict) and intent.get("required") is True:
            manifest_path = workflow / "prototype/manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if intent.get("status") == "approved":
                manifest.update(status="approved", approval=intent.get("approval"))
            if mutate_manifest is not None:
                mutate_manifest(manifest)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            if mutate_artifact is not None:
                mutate_artifact(workflow / "prototype/index.html")
        return VALIDATOR.validate(data, phase, workflow)[0]


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
    def test_template_is_valid_draft_and_requires_fresh_approval_before_execution(self) -> None:
        raw = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(errors(raw, "draft"), [])
        self.assertEqual(raw["lifecycle"]["status"], "draft")
        self.assertEqual(raw["intent_baseline"]["status"], "proposed")
        self.assertIsNone(raw["intent_baseline"]["digest"])
        self.assertIsNone(raw["intent_baseline"]["approval"])
        for node in raw["nodes"]:
            if node["kind"] == "expand":
                continue
            self.assertIn(node["status"], {"pending", "blocked"})
            self.assertEqual(node["runtime"].get("tokens_used"), 0)
            for field in ("started_at", "updated_at", "completed_at", "summary"):
                self.assertIsNone(node["runtime"].get(field))

        review = json.loads((TEMPLATE.parent / "question-review.json").read_text(encoding="utf-8"))
        self.assertEqual(review["status"], "draft")
        self.assertIsNone(review["graph_digest"])
        self.assertIsNone(review["reviewed_at"])
        self.assertTrue(all(item["result"] == "pending" for item in review["challenges"]))

        manifest = json.loads((TEMPLATE.parent / "prototype/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "proposed")
        self.assertIsNone(manifest["approval"])

        runtime = json.loads((TEMPLATE.parent / "runtime.json").read_text(encoding="utf-8"))
        self.assertEqual(runtime["scheduler"]["status"], "idle")
        self.assertTrue(all(value is False for value in runtime["authority"].values()))
        self.assertEqual(runtime["authority_grants"], {})
        self.assertEqual(runtime["delivery"]["status"], "not_required")
        self.assertEqual(runtime["checkout_guard"]["status"], "uninitialized")
        integrity_only = copy.deepcopy(raw)
        integrity_only["integrity"].update(
            status="locked",
            plan_digest="sha256:" + "1" * 64,
            runner_digest="sha256:" + "2" * 64,
        )
        self.assertTrue(any("question_gate.review.status" in item for item in errors(integrity_only)))
        self.assertTrue(any("intent_baseline.status" in item for item in errors(integrity_only)))
        self.assertEqual(errors(graph()), [])

    def test_missing_or_unapproved_intent_fails(self) -> None:
        missing = graph()
        del missing["intent_baseline"]
        self.assertTrue(any("intent_baseline" in item for item in errors(missing)))

        proposed = graph()
        proposed["intent_baseline"].update(status="proposed", digest=None, approval=None)
        self.assertTrue(any("approved" in item for item in errors(proposed)))

    def test_approved_intent_is_bound_to_current_manifest_and_artifact(self) -> None:
        fake_digest = graph()
        fake_digest["intent_baseline"]["digest"] = "sha256:" + "5" * 64
        self.assertTrue(any("approved manifest digest" in item for item in errors(fake_digest)))

        manifest_not_approved = graph()
        self.assertTrue(any(
            "manifest.status" in item
            for item in errors(manifest_not_approved, mutate_manifest=lambda value: value.update(status="proposed"))
        ))

        artifact_drift = graph()
        self.assertTrue(any(
            "baseline artifact" in item
            for item in errors(artifact_drift, mutate_artifact=lambda path: path.write_text("drift\n", encoding="utf-8"))
        ))

    def test_approved_intent_rejects_semantic_manifest_drift(self) -> None:
        mutations = {
            "method": "Dry Run",
            "promotable": True,
            "fidelity": ["flow"],
            "mocked": [],
            "not_proven": ["authorization", "real API", "performance", "accessibility"],
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                self.assertTrue(any(
                    "approved manifest digest" in item
                    for item in errors(graph(), mutate_manifest=lambda manifest, f=field, v=value: manifest.update({f: v}))
                ))

    def test_question_gate_blocks_pivotal_unknowns_before_execution(self) -> None:
        missing = graph()
        del missing["question_gate"]
        self.assertTrue(any("question_gate" in item for item in errors(missing)))

        open_gate = graph()
        open_gate["question_gate"].update(
            status="open",
            unresolved_pivotal=[{"id": "Q1", "question": "Which public response contract is authoritative?", "impacts": ["scope", "intent_baseline"]}],
        )
        self.assertEqual(errors(open_gate, "draft"), [])
        self.assertTrue(any("clear before executable" in item for item in errors(open_gate)))

        false_clear = graph()
        false_clear["question_gate"]["unresolved_pivotal"] = [
            {"id": "Q1", "question": "Approve destructive migration?", "impacts": ["irreversible_action"]}
        ]
        self.assertTrue(any("clear status" in item for item in errors(false_clear)))

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

    def test_recursive_decomposition_bound_is_normative(self) -> None:
        valid = graph()
        node = next(node for node in valid["nodes"] if node["id"] == "B")
        node["decomposition_bound"] = {
            "policy": "ranking-function-v1",
            "name": "contract-points",
            "value": 3,
            "source_proposal": "sha256:" + "a" * 64,
        }
        self.assertEqual(errors(valid), [])

        invalid = copy.deepcopy(valid)
        next(node for node in invalid["nodes"] if node["id"] == "B")["decomposition_bound"]["value"] = 0
        self.assertTrue(any("decomposition_bound.value" in item for item in errors(invalid)))

    def test_shared_memory_contract_and_reservation(self) -> None:
        missing = graph()
        del missing["shared_memory"]
        self.assertTrue(any("shared_memory" in item for item in errors(missing)))

        claimed = graph()
        next(node for node in claimed["nodes"] if node["id"] == "D")["scope"]["artifacts"] = ["memory/capsules/D.json"]
        self.assertTrue(any("coordinator-reserved shared memory" in item for item in errors(claimed)))

    def test_executable_nodes_require_unique_locked_executors(self) -> None:
        missing = graph()
        next(node for node in missing["nodes"] if node["id"] == "D").pop("executor")
        self.assertTrue(any("executor" in item for item in errors(missing)))

        duplicate = graph()
        left = next(node for node in duplicate["nodes"] if node["id"] == "C")["executor"]
        right = next(node for node in duplicate["nodes"] if node["id"] == "D")["executor"]
        right["spec"] = left["spec"]
        self.assertTrue(any("already assigned" in item for item in errors(duplicate)))

        unlocked = graph()
        next(node for node in unlocked["nodes"] if node["id"] == "D")["executor"]["digest"] = None
        self.assertTrue(any("lock the executor spec" in item for item in errors(unlocked)))

    def test_integrity_contract_is_locked_and_verifier_owned(self) -> None:
        missing = graph()
        del missing["integrity"]
        self.assertTrue(any("integrity" in item for item in errors(missing)))

        proposed = graph()
        proposed["integrity"].update(status="proposed", plan_digest=None, runner_digest=None)
        self.assertTrue(any("locked before executable" in item for item in errors(proposed)))

        producer_owned = graph()
        next(node for node in producer_owned["nodes"] if node["id"] == "B")["scope"]["artifacts"] = ["evidence/attestations/producer"]
        self.assertTrue(any("non-verifier" in item for item in errors(producer_owned)))

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
