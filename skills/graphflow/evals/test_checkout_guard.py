#!/usr/bin/env python3
"""Adversarial regression tests for the primary-checkout trust boundary."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("graphflow_checkout_guard", ROOT / "scripts" / "checkout_guard.py")
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


class CheckoutGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Graphflow Test")
        self.git("config", "user.email", "graphflow-test@local.invalid")
        (self.repo / ".gitignore").write_text(".graphflow/\n", encoding="utf-8")
        (self.repo / "baseline.txt").write_text("baseline\n", encoding="utf-8")
        scoped = self.repo / "packages" / "contracts" / "src" / "publish-retry.ts"
        scoped.parent.mkdir(parents=True)
        scoped.write_text("export const baseline = true;\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")
        self.workflow = self.repo / ".graphflow" / "workflow"
        shutil.copytree(ROOT / "assets" / "workflow-template", self.workflow)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str) -> str:
        completed = subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True, check=True)
        return completed.stdout.strip()

    def request(self, snapshot: dict[str, object]) -> tuple[Path, dict[str, object]]:
        runtime = json.loads((self.workflow / "runtime.json").read_text(encoding="utf-8"))
        request_id = runtime["checkout_guard"]["request_id"]
        self.assertEqual(snapshot["status"], "waiting_approval")
        path = self.workflow / "runtime" / "requests" / f"{request_id}.json"
        return path, json.loads(path.read_text(encoding="utf-8"))

    def decide(self, request: dict[str, object], decision: str) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "confirm_workflow.py"),
                str(self.workflow),
                "--request-id",
                str(request["request_id"]),
                "--digest",
                str(request["digest"]),
                "--decision",
                decision,
                "--answer",
                f"test {decision}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_clean_baseline_is_idempotent_and_workflow_artifacts_are_excluded(self) -> None:
        first = GUARD.advance(self.workflow, self.repo)
        second = GUARD.advance(self.workflow, self.repo)
        self.assertEqual(first["status"], "clear")
        self.assertEqual(second["status"], "clear")
        self.assertEqual(first["baseline_state_digest"], second["baseline_state_digest"])
        self.assertEqual(second["current_dirty_paths"], 0)

    def test_preexisting_dirty_state_is_preserved_but_later_change_blocks(self) -> None:
        (self.repo / "baseline.txt").write_text("user draft v1\n", encoding="utf-8")
        initial = GUARD.advance(self.workflow, self.repo)
        self.assertEqual(initial["baseline_dirty_paths"], 1)
        (self.repo / "baseline.txt").write_text("user draft v2\n", encoding="utf-8")
        drift = GUARD.advance(self.workflow, self.repo)
        self.assertEqual(drift["status"], "waiting_approval")
        self.assertEqual(drift["changes"][0]["path"], "baseline.txt")
        self.assertEqual(drift["changes"][0]["declared_owners"], [])

    def test_declared_node_scope_does_not_authorize_primary_checkout_mutation(self) -> None:
        GUARD.advance(self.workflow, self.repo)
        path = self.repo / "packages" / "contracts" / "src" / "publish-retry.ts"
        path.write_text("export const escaped = true;\n", encoding="utf-8")
        drift = GUARD.advance(self.workflow, self.repo)
        self.assertEqual(drift["status"], "waiting_approval")
        self.assertEqual(drift["changes"][0]["declared_owners"], ["B"])

    def test_exact_digest_approval_adopts_current_state_once(self) -> None:
        initial = GUARD.advance(self.workflow, self.repo)
        (self.repo / "outside.txt").write_text("concurrent user work\n", encoding="utf-8")
        drift = GUARD.advance(self.workflow, self.repo)
        request_path, request = self.request(drift)
        self.decide(request, "approved")
        adopted = GUARD.advance(self.workflow, self.repo)
        self.assertEqual(adopted["status"], "clear")
        consumed = json.loads(request_path.read_text(encoding="utf-8"))
        self.assertEqual(consumed["status"], "consumed")
        self.assertNotEqual(initial["baseline_state_digest"], adopted["baseline_state_digest"])

    def test_approval_is_superseded_if_checkout_changes_again(self) -> None:
        GUARD.advance(self.workflow, self.repo)
        (self.repo / "outside.txt").write_text("v1\n", encoding="utf-8")
        first_drift = GUARD.advance(self.workflow, self.repo)
        first_path, first_request = self.request(first_drift)
        self.decide(first_request, "approved")
        (self.repo / "outside.txt").write_text("v2\n", encoding="utf-8")
        second_drift = GUARD.advance(self.workflow, self.repo)
        second_path, second_request = self.request(second_drift)
        self.assertNotEqual(first_request["request_id"], second_request["request_id"])
        self.assertEqual(json.loads(first_path.read_text(encoding="utf-8"))["status"], "superseded")
        self.assertEqual(second_path.name, f"{second_request['request_id']}.json")

    def test_rejection_blocks_until_checkout_returns_to_baseline(self) -> None:
        GUARD.advance(self.workflow, self.repo)
        (self.repo / "baseline.txt").write_text("drift\n", encoding="utf-8")
        drift = GUARD.advance(self.workflow, self.repo)
        request_path, request = self.request(drift)
        self.decide(request, "rejected")
        blocked = GUARD.advance(self.workflow, self.repo)
        self.assertEqual(blocked["status"], "blocked")
        self.git("restore", "baseline.txt")
        clear = GUARD.advance(self.workflow, self.repo)
        self.assertEqual(clear["status"], "clear")
        self.assertEqual(json.loads(request_path.read_text(encoding="utf-8"))["status"], "superseded")

    def test_clean_commit_is_detected_through_head_and_git_metadata(self) -> None:
        GUARD.advance(self.workflow, self.repo)
        (self.repo / "baseline.txt").write_text("committed drift\n", encoding="utf-8")
        self.git("add", "baseline.txt")
        self.git("commit", "-qm", "concurrent commit")
        drift = GUARD.advance(self.workflow, self.repo)
        self.assertEqual(drift["status"], "waiting_approval")
        self.assertTrue(drift["head_changed"])
        self.assertTrue(drift["git_metadata_changed"])
        self.assertEqual(drift["changes"], [])

    def test_baseline_artifact_tampering_fails_closed(self) -> None:
        GUARD.advance(self.workflow, self.repo)
        path = self.workflow / "runtime" / "checkout-baseline.json"
        baseline = json.loads(path.read_text(encoding="utf-8"))
        baseline["captured_at"] = "tampered"
        path.write_text(json.dumps(baseline), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "baseline digest"):
            GUARD.advance(self.workflow, self.repo)

    def test_initial_baseline_refuses_preexisting_durable_results(self) -> None:
        result = self.workflow / "runtime" / "results" / "B.json"
        result.parent.mkdir(parents=True)
        result.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "durable node results"):
            GUARD.advance(self.workflow, self.repo)


if __name__ == "__main__":
    unittest.main()
