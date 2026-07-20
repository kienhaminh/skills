#!/usr/bin/env python3
"""Regression tests for canonical editing and confirmation-gated reframing."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "workflow-template"
SPEC = importlib.util.spec_from_file_location("graphflow_reframe", ROOT / "scripts" / "reframe_flow.py")
assert SPEC and SPEC.loader
REFRAME = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REFRAME)


class ReframeFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_json(self, name: str, value: dict) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")
        return path

    def test_canonical_graph_can_be_edited_without_reframe(self) -> None:
        source = self.root / "canonical"
        shutil.copytree(TEMPLATE, source)
        output = self.root / "canonical-proposal.json"
        result = REFRAME.inspect(source, output, None)
        self.assertEqual(result["classification"], "canonical-graphflow-v3")
        self.assertFalse(result["confirmation_required"])

    def test_noncanonical_flow_requires_digest_bound_user_approval(self) -> None:
        source = self.write_json(
            "legacy.json",
            {"name": "Release flow", "steps": [{"id": "build"}, {"id": "ship"}], "transitions": [["build", "ship"]]},
        )
        source_before = source.read_bytes()
        proposal = self.root / "reframe" / "proposal.json"
        result = REFRAME.inspect(source, proposal, "release-flow")
        self.assertEqual(source.read_bytes(), source_before)
        self.assertEqual(result["classification"], "noncanonical-structured")
        self.assertTrue(result["confirmation_required"])
        proposal_value = json.loads(proposal.read_text(encoding="utf-8"))
        proposal_value["reframe_mapping"] = {
            "objective": "Release a build safely.",
            "non_goals": [],
            "requirements": [{"id": "R1", "text": "Build"}, {"id": "R2", "text": "Ship"}],
            "nodes": [{"id": "build"}, {"id": "ship"}],
            "dependencies": [["build", "ship"]],
            "scopes": {"build": "build artifacts", "ship": "release target"},
            "prototype_gate": {"required": False, "reason": "deterministic flow migration"},
            "verification_oracles": ["build artifact exists", "release dry-run passes"],
            "unknowns": [],
            "discarded_semantics": [],
        }
        proposal.write_text(json.dumps(proposal_value, indent=2), encoding="utf-8")
        proposal_digest = REFRAME.file_digest(proposal)
        approval = self.write_json(
            "approval.json",
            {
                "schema_version": 1,
                "proposal_digest": proposal_digest,
                "decision": "approved",
                "approved_by": "user",
                "approved_at": "2026-07-19T00:00:00Z",
            },
        )
        self.assertTrue(REFRAME.verify_approval(proposal, approval)["approved"])

        value = json.loads(proposal.read_text(encoding="utf-8"))
        value["candidate_summary"]["objective_candidate"] = "Changed after approval"
        proposal.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match"):
            REFRAME.verify_approval(proposal, approval)

    def test_opaque_flow_requires_explicit_target_id(self) -> None:
        source = self.root / "flow.mmd"
        source.write_text("flowchart LR\nA --> B\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "workflow-id"):
            REFRAME.inspect(source, self.root / "proposal.json", None)


if __name__ == "__main__":
    unittest.main()
