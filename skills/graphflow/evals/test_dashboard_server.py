#!/usr/bin/env python3
"""Regression tests for dashboard ownership and shared-memory exposure."""

from __future__ import annotations

import importlib.util
import json
import shutil
import socket
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("workflow_dashboard", ROOT / "scripts" / "serve_dashboard.py")
assert SPEC and SPEC.loader
DASHBOARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DASHBOARD)


class DashboardServerTests(unittest.TestCase):
    def test_memory_snapshot_is_exposed_but_event_log_is_not(self) -> None:
        self.assertIn("/memory/state.json", DASHBOARD.ALLOWED_PATHS)
        self.assertIn("/runtime.json", DASHBOARD.ALLOWED_PATHS)
        self.assertIn("/requests.json", DASHBOARD.ALLOWED_PATHS)
        self.assertIn("/progress.json", DASHBOARD.ALLOWED_PATHS)
        self.assertIn("/workspaces.json", DASHBOARD.ALLOWED_PATHS)
        self.assertIn("/checkout.json", DASHBOARD.ALLOWED_PATHS)
        self.assertNotIn("/memory/events.jsonl", DASHBOARD.ALLOWED_PATHS)
        self.assertNotIn("/runtime/events.jsonl", DASHBOARD.ALLOWED_PATHS)

    def test_dashboard_renders_decomposition_status_without_failure_detail(self) -> None:
        source = (ROOT / "assets" / "workflow-template" / "dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("decomposition.status", source)
        self.assertIn("decomposition.revision", source)
        self.assertNotIn("decomposition.failure", source)

    def test_confirmation_projection_omits_user_answer_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requests = root / "runtime" / "requests"
            requests.mkdir(parents=True)
            (requests / "q.json").write_text(
                '{"request_id":"q","node_id":"D","status":"pending","question":"Approve?","digest":"secret-binding","response":{"answer":"private"}}',
                encoding="utf-8",
            )
            projection = DASHBOARD.confirmation_projection(root)
            self.assertEqual(projection[0]["question"], "Approve?")
            self.assertNotIn("digest", projection[0])
            self.assertNotIn("response", projection[0])

    def test_owned_command_resolves_workflow_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            command = f"python3 {ROOT / 'scripts' / 'serve_dashboard.py'} serve {root} --port 8765"
            self.assertTrue(DASHBOARD.command_owns_root(command, root))
            self.assertFalse(DASHBOARD.command_owns_root(command, root / "other"))

    def test_tmp_alias_is_canonicalized_when_available(self) -> None:
        alias = Path("/tmp/workflow-dashboard-alias")
        canonical = alias.resolve()
        command = f"python3 {ROOT / 'scripts' / 'serve_dashboard.py'} serve {alias}"
        self.assertTrue(DASHBOARD.command_owns_root(command, canonical))

    def test_loopback_exposes_sanitized_progress_and_workspace_projections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workflow"
            shutil.copytree(ROOT / "assets" / "workflow-template", root)
            DASHBOARD.progress_state.update(root, "B", "running", workspace_ref="workspace-b")
            with socket.socket() as probe:
                try:
                    probe.bind((DASHBOARD.HOST, 0))
                except PermissionError:
                    self.skipTest("sandbox forbids loopback binding")
                port = int(probe.getsockname()[1])
            server, _ = DASHBOARD.bind_server(root, port, port)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://{DASHBOARD.HOST}:{port}/progress.json", timeout=2) as response:
                    progress = json.loads(response.read())
                with urllib.request.urlopen(f"http://{DASHBOARD.HOST}:{port}/workspaces.json", timeout=2) as response:
                    workspaces = json.loads(response.read())
                with urllib.request.urlopen(f"http://{DASHBOARD.HOST}:{port}/checkout.json", timeout=2) as response:
                    checkout = json.loads(response.read())
                self.assertEqual(progress["progress"][0]["phase"], "running")
                self.assertTrue(any(item["workspace_id"] == "workspace-b" for item in workspaces["workspaces"]))
                self.assertNotIn("prompt", json.dumps(progress))
                self.assertNotIn("path", json.dumps(workspaces))
                self.assertNotIn("cache_dir", json.dumps(workspaces))
                self.assertEqual(checkout["status"], "uninitialized")
                self.assertNotIn("repo_root", checkout)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
