#!/usr/bin/env python3
"""Adversarial tests for Graphflow workspace trust boundaries."""

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
TEMPLATE = ROOT / "assets" / "workflow-template"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("graphflow_workspace_manager", ROOT / "scripts" / "workspace_manager.py")
assert SPEC and SPEC.loader
WORKSPACES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKSPACES)


def run(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


class WorkspaceManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        run(self.repo, "init", "-q")
        run(self.repo, "config", "user.name", "Graphflow Eval")
        run(self.repo, "config", "user.email", "eval@graphflow.invalid")
        for relative in (
            "packages/contracts/src/publish-retry.ts",
            "apps/server/src/publish/bulk-retry/.keep",
            "apps/web/app/admin/publish-queue/bulk-retry/.keep",
        ):
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("base\n", encoding="utf-8")
        run(self.repo, "add", ".")
        run(self.repo, "commit", "-qm", "base")
        self.workflow = self.root / "workflow"
        shutil.copytree(TEMPLATE, self.workflow)
        WORKSPACES.initialize(self.workflow)
        self.graph = json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))
        self.nodes = {node["id"]: node for node in self.graph["nodes"]}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def provision(self, ref: str) -> dict:
        return WORKSPACES.provision_entry(self.workflow, self.repo, ref)

    def test_worktree_is_repo_bound_branch_bound_and_clean(self) -> None:
        entry = self.provision("workspace-b")
        path = Path(entry["path"])
        self.assertNotEqual(path, self.repo)
        self.assertEqual(WORKSPACES.common_dir(path), WORKSPACES.common_dir(self.repo))
        self.assertEqual(WORKSPACES.branch(path), entry["branch"])
        self.assertEqual(WORKSPACES.changed_files(path), [])
        self.assertTrue(entry["workflow_owned"])

    def test_scope_rejects_outside_write_and_worker_ref_mutation(self) -> None:
        entry = self.provision("workspace-b")
        path = Path(entry["path"])
        before = WORKSPACES.snapshot(path)
        outside = path / "apps/server/src/publish/escape.ts"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("escape\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside scope"):
            WORKSPACES.verify_scope(path, self.nodes["B"], before)

        outside.unlink()
        run(path, "branch", "worker-mutated-ref")
        with self.assertRaisesRegex(ValueError, "shared refs"):
            WORKSPACES.verify_scope(path, self.nodes["B"], before)

    def test_worker_cannot_stage_or_change_protected_git_metadata(self) -> None:
        entry = self.provision("workspace-b")
        path = Path(entry["path"])
        before = WORKSPACES.snapshot(path)
        (path / "packages/contracts/src/publish-retry.ts").write_text("staged-by-worker\n", encoding="utf-8")
        run(path, "add", "packages/contracts/src/publish-retry.ts")
        with self.assertRaisesRegex(ValueError, "protected Git metadata"):
            WORKSPACES.verify_scope(path, self.nodes["B"], before)

    def test_changed_symlink_fails_closed(self) -> None:
        entry = self.provision("workspace-b")
        path = Path(entry["path"])
        before = WORKSPACES.snapshot(path)
        owned = path / "packages/contracts/src/publish-retry.ts"
        owned.unlink()
        owned.symlink_to("../../../../apps/server/src/publish/bulk-retry/.keep")
        with self.assertRaisesRegex(ValueError, "symlinks require an explicit"):
            WORKSPACES.verify_scope(path, self.nodes["B"], before)

    def test_checkpoint_rechecks_scope_and_is_crash_idempotent(self) -> None:
        entry = self.provision("workspace-b")
        path = Path(entry["path"])
        before = WORKSPACES.snapshot(path)
        owned = path / "packages/contracts/src/publish-retry.ts"
        owned.write_text("accepted\n", encoding="utf-8")
        report = WORKSPACES.verify_scope(path, self.nodes["B"], before)
        owned.write_text("changed-after-check\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale checkpoint"):
            WORKSPACES.checkpoint(self.workflow, "workspace-b", "B", report)

        owned.write_text("accepted\n", encoding="utf-8")
        first = WORKSPACES.checkpoint(self.workflow, "workspace-b", "B", report)
        second = WORKSPACES.checkpoint(self.workflow, "workspace-b", "B", report)
        self.assertEqual(first, second)
        self.assertEqual(WORKSPACES.changed_files(path), [])

    def test_dependency_checkpoint_flows_to_consumer_then_integration(self) -> None:
        entry = self.provision("workspace-b")
        path = Path(entry["path"])
        before = WORKSPACES.snapshot(path)
        (path / "packages/contracts/src/publish-retry.ts").write_text("from-b\n", encoding="utf-8")
        report = WORKSPACES.verify_scope(path, self.nodes["B"], before)
        WORKSPACES.checkpoint(self.workflow, "workspace-b", "B", report)

        consumer = self.provision("workspace-c")
        consumer_path = Path(consumer["path"])
        self.assertEqual((consumer_path / "packages/contracts/src/publish-retry.ts").read_text(encoding="utf-8"), "from-b\n")
        self.assertEqual(WORKSPACES.load_registry(self.workflow)["entries"]["workspace-b"]["status"], "checkpointed")

        self.provision("workspace-e")
        self.assertEqual(WORKSPACES.load_registry(self.workflow)["entries"]["workspace-b"]["status"], "integrated")
        cleaned = WORKSPACES.cleanup_entry(self.workflow, self.repo, "workspace-b")
        self.assertEqual(cleaned["status"], "cleaned")
        self.assertFalse(path.exists())

    def test_allocation_collision_is_rejected(self) -> None:
        registry_path = self.workflow / "runtime" / "workspaces.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["entries"]["workspace-c"]["allocations"]["port_offset"] = 100
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "allocation collision"):
            WORKSPACES.load_registry(self.workflow)


if __name__ == "__main__":
    unittest.main()
