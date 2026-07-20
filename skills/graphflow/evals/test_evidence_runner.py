#!/usr/bin/env python3
"""Regression tests for proof-carrying workflow completion."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "workflow-template"
SPEC = importlib.util.spec_from_file_location("workflow_evidence", ROOT / "scripts" / "evidence_runner.py")
assert SPEC and SPEC.loader
EVIDENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVIDENCE)
from skills.graphflow.evals.fixture_support import approve_intent_and_review


class EvidenceRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workflow = Path(self.temporary.name) / "workflow"
        shutil.copytree(TEMPLATE, self.workflow)
        self.repo = Path(self.temporary.name) / "repo"
        for path in (
            "packages/contracts/src/publish-retry.ts",
            "apps/server/src/publish/bulk-retry/.keep",
            "apps/web/app/admin/publish-queue/bulk-retry/.keep",
            "apps/server/src/publish/bulk-retry.integration.ts",
        ):
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("fixture\n", encoding="utf-8")
        plan_path = self.workflow / "integrity" / "verification-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        fixture_by_check = {
            "CHK-R1-CONTRACT": "packages/contracts/src/publish-retry.ts",
            "CHK-R2-SERVER-NEGATIVE": "apps/server/src/publish/bulk-retry",
            "CHK-R3-UI": "apps/web/app/admin/publish-queue/bulk-retry",
            "CHK-R4-INTEGRATION": "apps/server/src/publish/bulk-retry.integration.ts",
            "CHK-R5-FALSIFICATION": "packages/contracts/src/publish-retry.ts",
        }
        for check in plan["checks"]:
            fixture = fixture_by_check[check["id"]]
            check["argv"] = ["python3", "-c", f"from pathlib import Path; raise SystemExit(0 if Path('{fixture}').exists() else 1)"]
        self.write_json(plan_path, plan)
        approve_intent_and_review(self.workflow)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_json(self, path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")

    def test_lock_is_idempotent_and_plan_weakening_is_rejected(self) -> None:
        first = EVIDENCE.command_lock(self.workflow, self.repo)
        second = EVIDENCE.command_lock(self.workflow, self.repo)
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])

        plan_path = self.workflow / "integrity" / "verification-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["checks"] = plan["checks"][:-1]
        self.write_json(plan_path, plan)
        with self.assertRaisesRegex(ValueError, "locked oracle changed"):
            EVIDENCE.command_lock(self.workflow, self.repo)

    def test_runner_rejects_mutation_of_watched_state(self) -> None:
        plan_path = self.workflow / "integrity" / "verification-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["checks"][0]["argv"] = [
            "python3", "-c",
            "from pathlib import Path; p=Path('packages/contracts/src/publish-retry.ts'); p.write_text('changed')",
        ]
        self.write_json(plan_path, plan)
        EVIDENCE.command_lock(self.workflow, self.repo)
        with self.assertRaisesRegex(ValueError, "state_mutated=True"):
            EVIDENCE.command_run(self.workflow, self.repo, "CHK-R1-CONTRACT")
        envelope = json.loads((self.workflow / "evidence" / "attestations" / "CHK-R1-CONTRACT.json").read_text(encoding="utf-8"))
        self.assertFalse(envelope["passed"])

    def test_complete_requires_current_evidence_and_independent_review(self) -> None:
        EVIDENCE.command_lock(self.workflow, self.repo)
        for check_id in (
            "CHK-R1-CONTRACT",
            "CHK-R2-SERVER-NEGATIVE",
            "CHK-R3-UI",
            "CHK-R4-INTEGRATION",
            "CHK-R5-FALSIFICATION",
        ):
            EVIDENCE.command_run(self.workflow, self.repo, check_id)

        plan = json.loads((self.workflow / "integrity" / "verification-plan.json").read_text(encoding="utf-8"))
        review_input = {
            "schema_version": 1,
            "verifier_node": "F",
            "producer_nodes": ["B", "C", "D", "E"],
            "outcome": "pass",
            "challenge_classes": ["negative", "boundary"],
            "evidence_attestations": [check["attestation"] for check in plan["checks"] if check["critical"]],
            "limitations": [],
        }
        review_path = Path(self.temporary.name) / "review.json"
        self.write_json(review_path, review_input)
        EVIDENCE.command_record_review(self.workflow, self.repo, review_path)

        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["lifecycle"]["status"] = "complete"
        for node in graph["nodes"]:
            if node["kind"] != "expand":
                node["status"] = "complete"
        checks = {requirement: check for check in plan["checks"] for requirement in check["requirement_ids"]}
        graph["verification"] = {
            "outcome": "verified",
            "claims": [
                {
                    "id": f"C-{requirement['id']}",
                    "requirement_id": requirement["id"],
                    "statement": requirement["text"],
                    "state": "verified",
                    "confidence": "high",
                    "evidence": [{"check": checks[requirement["id"]]["id"], "artifact": checks[requirement["id"]]["attestation"]}],
                    "limitations": [],
                }
                for requirement in graph["objective"]["requirements"]
            ],
        }
        self.write_json(graph_path, graph)
        report = EVIDENCE.command_validate(self.workflow, self.repo, "complete")
        self.assertTrue(report["complete"])

        watched = self.repo / "packages" / "contracts" / "src" / "publish-retry.ts"
        watched.write_text("stale\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "watched state changed or is stale"):
            EVIDENCE.command_validate(self.workflow, self.repo, "complete")

    def test_manual_attestation_is_not_accepted(self) -> None:
        locked = EVIDENCE.command_lock(self.workflow, self.repo)
        fake = {
            "runner": EVIDENCE.RUNNER_ID,
            "runner_digest": locked["runner_digest"],
            "check_id": "CHK-R1-CONTRACT",
            "plan_digest": locked["plan_digest"],
            "contract_digest": locked["contract_digest"],
            "passed": True,
        }
        self.write_json(self.workflow / "evidence" / "attestations" / "CHK-R1-CONTRACT.json", fake)
        graph, plan, lock, _ = EVIDENCE.load_locked(self.workflow, self.repo, "executable")
        check = plan["checks"][0]
        errors = EVIDENCE.validate_attestation(self.workflow, self.repo, check, lock["plan_digest"], lock["contract_digest"])
        self.assertTrue(any("command context" in error or "invalid descriptor" in error for error in errors))

    def test_high_integrity_external_gate_requires_exact_protected_provenance(self) -> None:
        graph = json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))
        verifier = json.loads(json.dumps(next(node for node in graph["nodes"] if node["id"] == "F")))
        verifier["id"] = "G"
        graph["nodes"].append(verifier)
        plan = json.loads((self.workflow / "integrity" / "verification-plan.json").read_text(encoding="utf-8"))
        mutation = json.loads(json.dumps(plan["checks"][0]))
        mutation.update(id="CHK-MUTATION", requirement_ids=["R1"], **{"class": "mutation", "verifier_node": "G", "attestation": "evidence/attestations/CHK-MUTATION.json"})
        plan["checks"].append(mutation)
        plan["level"] = "high"
        graph["integrity"]["level"] = "high"
        plan["challenge_policy"] = {"required_classes": ["negative", "boundary", "mutation"], "mutation_required": True}
        plan["separation_of_duties"]["verifier_nodes"] = ["F", "G"]
        plan["separation_of_duties"]["min_independent_verifiers"] = 2
        provenance = {
            "provider": "github-actions",
            "repository": "owner/repo",
            "commit_sha": "a" * 40,
            "workflow_id": "verify.yml",
            "run_id": "12345",
            "url": "https://github.com/owner/repo/actions/runs/12345",
            "attestation_digest": "sha256:" + "b" * 64,
            "protected": True,
        }
        artifact_path = self.workflow / "evidence/external/ci.json"
        artifact_value = {"status": "passed", "provenance": {**provenance, "run_id": "forged"}}
        self.write_json(artifact_path, artifact_value)
        plan["external_gate"] = {
            "required": True,
            "status": "passed",
            "artifact": "evidence/external/ci.json",
            "digest": EVIDENCE.file_digest(artifact_path),
            "provenance": provenance,
        }
        self.assertEqual(EVIDENCE.validate_plan(plan, graph), [])

        plan_digest = EVIDENCE.json_digest(plan)
        graph["integrity"].update(status="locked", plan_digest=plan_digest, runner_digest=EVIDENCE.runner_digest())
        contract_digest = EVIDENCE.canonical_graph_digest(graph)
        lock = {
            "schema_version": 1,
            "workflow_id": graph["workflow_id"],
            "status": "locked",
            "plan_digest": plan_digest,
            "runner_digest": EVIDENCE.runner_digest(),
            "contract_digest": contract_digest,
            "locked_at": "2026-01-01T00:00:00Z",
        }
        errors = EVIDENCE.validate_lock(graph, plan, lock, complete=True, workflow_dir=self.workflow)
        self.assertIn("plan.external_gate: artifact does not match protected provider provenance", errors)

        artifact_value["provenance"] = provenance
        self.write_json(artifact_path, artifact_value)
        plan["external_gate"]["digest"] = EVIDENCE.file_digest(artifact_path)
        plan_digest = EVIDENCE.json_digest(plan)
        graph["integrity"]["plan_digest"] = plan_digest
        contract_digest = EVIDENCE.canonical_graph_digest(graph)
        lock.update(plan_digest=plan_digest, contract_digest=contract_digest)
        self.assertEqual(EVIDENCE.validate_lock(graph, plan, lock, complete=True, workflow_dir=self.workflow), [])


if __name__ == "__main__":
    unittest.main()
