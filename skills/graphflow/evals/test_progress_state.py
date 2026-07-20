#!/usr/bin/env python3
"""Tests for sanitized coordinator-owned progress projections."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("graphflow_progress", ROOT / "scripts" / "progress_state.py")
assert SPEC and SPEC.loader
PROGRESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROGRESS)


class ProgressStateTests(unittest.TestCase):
    def test_update_is_sanitized_atomic_snapshot_plus_append_only_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = PROGRESS.update(root, "B", "running", workspace_ref="workspace-b", heartbeat_at="2026-01-01T00:00:00Z")
            second = PROGRESS.update(root, "B", "scope_accepted", workspace_ref="workspace-b", changed_files=["owned/file.ts"])
            snapshot = json.loads((root / "runtime/progress/B.json").read_text(encoding="utf-8"))
            events = (root / "runtime/progress/events.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(snapshot, second)
            self.assertEqual(len(events), 2)
            self.assertEqual(json.loads(events[0]), first)
            self.assertEqual(PROGRESS.projection(root), [second])
            PROGRESS.update(root, "C", "rejected", blocker="private failure detail")
            rejected = next(item for item in PROGRESS.projection(root) if item["node_id"] == "C")
            self.assertNotIn("blocker", rejected)

    def test_unsafe_or_reasoning_fields_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "unsafe fields"):
                PROGRESS.update(root, "B", "running", prompt="secret")
            with self.assertRaisesRegex(ValueError, "unsupported progress phase"):
                PROGRESS.update(root, "B", "thinking")

    def test_completion_requires_observed_non_compensatory_trust_phases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            graph = {
                "integrity": {"level": "medium"},
                "nodes": [
                    {"id": "B", "kind": "execute", "status": "complete", "scope": {"write": ["owned"]}},
                    {"id": "F", "kind": "verify", "status": "complete", "scope": {"write": []}},
                ],
            }
            PROGRESS.update(root, "B", "scope_accepted")
            PROGRESS.update(root, "B", "evidence_passed")
            PROGRESS.update(root, "B", "accepted")
            PROGRESS.update(root, "F", "scope_accepted")
            PROGRESS.update(root, "F", "evidence_passed")
            errors = PROGRESS.validate_completion(root, graph, {"B": "worktree", "F": "verifier"})
            self.assertEqual(errors, [
                "node F: missing independent verification phase",
                "node F: coordinator terminal progress snapshot is not accepted",
            ])
            PROGRESS.update(root, "F", "independently_verified")
            self.assertEqual(PROGRESS.validate_completion(root, graph, {"B": "worktree", "F": "verifier"}), [])


if __name__ == "__main__":
    unittest.main()
