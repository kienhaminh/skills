#!/usr/bin/env python3
"""Regression tests for dashboard ownership and shared-memory exposure."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("workflow_dashboard", ROOT / "scripts" / "serve_dashboard.py")
assert SPEC and SPEC.loader
DASHBOARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DASHBOARD)


class DashboardServerTests(unittest.TestCase):
    def test_memory_snapshot_is_exposed_but_event_log_is_not(self) -> None:
        self.assertIn("/memory/state.json", DASHBOARD.ALLOWED_PATHS)
        self.assertNotIn("/memory/events.jsonl", DASHBOARD.ALLOWED_PATHS)

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


if __name__ == "__main__":
    unittest.main()
