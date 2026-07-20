#!/usr/bin/env python3
"""Regression tests for shared workflow memory."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "workflow-template"
SPEC = importlib.util.spec_from_file_location("workflow_memory", ROOT / "scripts" / "memory_state.py")
assert SPEC and SPEC.loader
MEMORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MEMORY)


class SharedMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workflow = Path(self.temporary.name) / "workflow"
        shutil.copytree(TEMPLATE, self.workflow)
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_delta(self, value: dict, name: str = "delta.json") -> Path:
        path = Path(self.temporary.name) / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def entry(self, *, entry_id: str = "M-F-1", kind: str = "fact", pivotal: bool = False, summary: str = "Focused verification passed.") -> dict:
        evidence = self.workflow / "evidence" / "memory-check.json"
        evidence.parent.mkdir(exist_ok=True)
        evidence.write_text(json.dumps({"runner": "workflow-evidence-runner-v1", "passed": True}), encoding="utf-8")
        digest = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
        return {
            "id": entry_id,
            "kind": kind,
            "namespace": "verification.publish.bulk-retry.memory",
            "summary": summary,
            "status": "active",
            "evidence_state": "verified" if kind != "question" else "inferred",
            "confidence": "high" if kind != "question" else "low",
            "owner_node": "F",
            "requirement_ids": ["R5"],
            "relevant_nodes": ["F"],
            "artifact_refs": [{"path": "evidence/memory-check.json", "digest": digest}] if kind != "question" else [],
            "pivotal": pivotal,
            "supersedes": None,
        }

    def delta(self, base: int, *, add: list[dict] | None = None, supersede: list[str] | None = None, resolve: list[str] | None = None) -> dict:
        return {
            "schema_version": 1,
            "base_revision": base,
            "author_node": "F",
            "add": add or [],
            "supersede": supersede or [],
            "resolve": resolve or [],
        }

    def test_init_validate_replay_and_capsule(self) -> None:
        MEMORY.command_init(self.workflow, self.repo)
        MEMORY.command_apply(self.workflow, self.repo, self.write_delta(self.delta(0, add=[self.entry()])))
        report = MEMORY.command_validate(self.workflow, self.repo, "active", True)
        capsule = MEMORY.command_view(self.workflow, self.repo, "F", 20, 6000, None)
        replay = MEMORY.command_replay(self.workflow, self.repo, True)
        self.assertTrue(report["valid"])
        self.assertEqual([entry["id"] for entry in capsule["entries"]], ["M-F-1"])
        self.assertTrue(replay["matched"])

    def test_stale_revision_and_foreign_namespace_are_rejected(self) -> None:
        MEMORY.command_init(self.workflow, self.repo)
        MEMORY.command_apply(self.workflow, self.repo, self.write_delta(self.delta(0, add=[self.entry()])))
        with self.assertRaisesRegex(ValueError, "stale base_revision"):
            MEMORY.command_apply(self.workflow, self.repo, self.write_delta(self.delta(0), "stale.json"))

        foreign = self.entry(entry_id="M-F-2")
        foreign["namespace"] = "ui.publish.bulk-retry"
        with self.assertRaisesRegex(ValueError, "does not own this namespace"):
            MEMORY.command_apply(self.workflow, self.repo, self.write_delta(self.delta(1, add=[foreign]), "foreign.json"))

    def test_revision_change_invalidates_materialized_capsules(self) -> None:
        MEMORY.command_init(self.workflow, self.repo)
        MEMORY.command_apply(self.workflow, self.repo, self.write_delta(self.delta(0, add=[self.entry()])))
        MEMORY.command_view(self.workflow, self.repo, "F", 20, 6000, None)
        result = MEMORY.command_apply(self.workflow, self.repo, self.write_delta(self.delta(1, resolve=["M-F-1"]), "resolve.json"))
        self.assertEqual(result["invalidated_capsules"], ["F.json"])
        self.assertFalse((self.workflow / "memory" / "capsules" / "F.json").exists())

    def test_validation_rejects_stale_capsule(self) -> None:
        MEMORY.command_init(self.workflow, self.repo)
        capsule = MEMORY.command_view(self.workflow, self.repo, "F", 20, 6000, None)
        capsule["memory_revision"] = 99
        (self.workflow / "memory" / "capsules" / "F.json").write_text(json.dumps(capsule), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale revision"):
            MEMORY.command_validate(self.workflow, self.repo, "active", False)

    def test_complete_rejects_pivotal_question(self) -> None:
        MEMORY.command_init(self.workflow, self.repo)
        question = self.entry(kind="question", pivotal=True)
        MEMORY.command_apply(self.workflow, self.repo, self.write_delta(self.delta(0, add=[question])))
        with self.assertRaisesRegex(ValueError, "pivotal questions remain active"):
            MEMORY.command_validate(self.workflow, self.repo, "complete", False)

    def test_resolve_compact_and_replay(self) -> None:
        MEMORY.command_init(self.workflow, self.repo)
        MEMORY.command_apply(self.workflow, self.repo, self.write_delta(self.delta(0, add=[self.entry()])))
        MEMORY.command_apply(self.workflow, self.repo, self.write_delta(self.delta(1, resolve=["M-F-1"]), "resolve.json"))
        compacted = MEMORY.command_compact(self.workflow, self.repo)
        replayed = MEMORY.command_replay(self.workflow, self.repo, True)
        self.assertEqual(compacted["removed"], ["M-F-1"])
        self.assertTrue(replayed["matched"])

    def test_graph_change_requires_explicit_bind(self) -> None:
        MEMORY.command_init(self.workflow, self.repo)
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["objective"]["statement"] += " Updated."
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "graph_digest"):
            MEMORY.command_validate(self.workflow, self.repo, "active", False)
        rebound = MEMORY.command_bind(self.workflow, self.repo)
        self.assertTrue(rebound["changed"])
        self.assertTrue(MEMORY.command_validate(self.workflow, self.repo, "active", False)["valid"])

    def test_runtime_status_change_does_not_stale_semantic_binding(self) -> None:
        MEMORY.command_init(self.workflow, self.repo)
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        next(node for node in graph["nodes"] if node["id"] == "D")["runtime"]["summary"] = "Dispatched."
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        self.assertTrue(MEMORY.command_validate(self.workflow, self.repo, "active", False)["valid"])

    def test_secret_like_summary_is_rejected(self) -> None:
        MEMORY.command_init(self.workflow, self.repo)
        leaked = self.entry(summary="api_key=should-not-be-stored")
        with self.assertRaisesRegex(ValueError, "sanitized"):
            MEMORY.command_apply(self.workflow, self.repo, self.write_delta(self.delta(0, add=[leaked])))

    def test_producer_cannot_mark_its_memory_verified(self) -> None:
        MEMORY.command_init(self.workflow, self.repo)
        producer = self.entry(entry_id="M-B-1")
        producer["owner_node"] = "B"
        producer["namespace"] = "node.B.result"
        producer["relevant_nodes"] = ["B"]
        delta = self.delta(0, add=[producer])
        delta["author_node"] = "B"
        with self.assertRaisesRegex(ValueError, "verified memory must be authored by a verify node"):
            MEMORY.command_apply(self.workflow, self.repo, self.write_delta(delta))

    def test_plain_file_cannot_back_verified_memory(self) -> None:
        MEMORY.command_init(self.workflow, self.repo)
        forged = self.entry(entry_id="M-F-FORGED")
        evidence = self.workflow / "evidence" / "memory-check.json"
        evidence.write_text(json.dumps({"passed": True}), encoding="utf-8")
        forged["artifact_refs"][0]["digest"] = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "evidence-runner attestation"):
            MEMORY.command_apply(self.workflow, self.repo, self.write_delta(self.delta(0, add=[forged])))


if __name__ == "__main__":
    unittest.main()
