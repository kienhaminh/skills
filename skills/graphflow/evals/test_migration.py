#!/usr/bin/env python3
"""Regression tests for non-destructive Graphflow legacy-to-v3 migration."""

from __future__ import annotations

import hashlib
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
SPEC = importlib.util.spec_from_file_location("graphflow_migration", ROOT / "scripts" / "migrate_workflow.py")
assert SPEC and SPEC.loader
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "legacy"
        self.target = self.root / "current"
        shutil.copytree(TEMPLATE, self.source)
        graph_path = self.source / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["version"] = 1
        del graph["question_gate"]
        graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_migration_preserves_source_and_requires_fresh_locks(self) -> None:
        source_digest = digest(self.source / "graph.json")
        report = MIGRATION.migrate(self.source, self.target)
        self.assertEqual(digest(self.source / "graph.json"), source_digest)
        graph = json.loads((self.target / "graph.json").read_text(encoding="utf-8"))
        runtime = json.loads((self.target / "runtime.json").read_text(encoding="utf-8"))
        result_schema = json.loads((self.target / "nodes" / "node-result.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(graph["version"], 3)
        self.assertEqual(graph["lifecycle"]["status"], "draft")
        self.assertEqual(graph["question_gate"]["review"]["status"], "required")
        self.assertEqual(graph["integrity"]["status"], "proposed")
        self.assertEqual(runtime["authority_grants"], {})
        self.assertEqual(runtime["delivery"]["adapter"], "ship-v1")
        self.assertEqual(runtime["delivery"]["status"], "not_required")
        self.assertEqual(runtime["checkout_guard"]["policy"], "primary-checkout-baseline-v1")
        self.assertEqual(runtime["checkout_guard"]["status"], "uninitialized")
        self.assertEqual(runtime["decomposition"]["policy"], "structural-decomposition-v1")
        self.assertEqual(runtime["decomposition"]["status"], "idle")
        self.assertEqual(result_schema["properties"]["schema_version"]["const"], 2)
        self.assertEqual(report["target_version"], 3)
        workspaces = json.loads((self.target / "runtime" / "workspaces.json").read_text(encoding="utf-8"))
        self.assertEqual(workspaces["workflow_id"], graph["workflow_id"])
        for node in graph["nodes"]:
            if node["kind"] == "expand":
                continue
            self.assertEqual(node["executor"]["digest"], digest(self.target / node["executor"]["spec"]))
            spec = json.loads((self.target / node["executor"]["spec"]).read_text(encoding="utf-8"))
            self.assertEqual(spec["schema_version"], 2)
            self.assertIn("workspace", spec)
            self.assertNotIn("cwd", spec)

    def test_migration_refuses_in_place_or_existing_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "differ from source"):
            MIGRATION.migrate(self.source, self.source)
        self.target.mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            MIGRATION.migrate(self.source, self.target)

    def test_v2_migration_adds_v3_workspace_trust_without_touching_source(self) -> None:
        graph_path = self.source / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["version"] = 2
        graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
        source_digest = digest(graph_path)
        report = MIGRATION.migrate(self.source, self.target)
        migrated = json.loads((self.target / "graph.json").read_text(encoding="utf-8"))
        registry = json.loads((self.target / "runtime/workspaces.json").read_text(encoding="utf-8"))
        self.assertEqual(report["source_version"], 2)
        self.assertEqual(migrated["version"], 3)
        self.assertEqual(migrated["execution_trust"]["workspace_registry"], "runtime/workspaces.json")
        self.assertTrue(all("patch_digest" in entry for entry in registry["entries"].values()))
        self.assertEqual(digest(graph_path), source_digest)

    def test_migration_removes_only_new_partial_target_on_failure(self) -> None:
        graph_path = self.source / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["nodes"][1]["executor"]["spec"] = "nodes/missing-executor.json"
        graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
        source_digest = digest(graph_path)

        with self.assertRaises((FileNotFoundError, ValueError)):
            MIGRATION.migrate(self.source, self.target)

        self.assertFalse(self.target.exists())
        self.assertEqual(digest(graph_path), source_digest)


if __name__ == "__main__":
    unittest.main()
