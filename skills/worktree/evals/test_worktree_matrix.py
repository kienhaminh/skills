#!/usr/bin/env python3
"""Unit tests for portable per-worktree environment mapping."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "worktree_matrix.py"
SPEC = importlib.util.spec_from_file_location("worktree_matrix", SCRIPT)
assert SPEC and SPEC.loader
MATRIX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MATRIX)
PREPARE_SCRIPT = Path(__file__).resolve().parent / "prepare_fixture.py"
PREPARE_SPEC = importlib.util.spec_from_file_location("worktree_prepare_fixture", PREPARE_SCRIPT)
assert PREPARE_SPEC and PREPARE_SPEC.loader
PREPARE = importlib.util.module_from_spec(PREPARE_SPEC)
PREPARE_SPEC.loader.exec_module(PREPARE)


class SlotEnvironmentTests(unittest.TestCase):
    def test_renders_repository_variable_names_without_shell_evaluation(self) -> None:
        context = {
            "slot": "2",
            "name": "feature-a",
            "port_offset": "200",
            "path": "/tmp/repo-a",
            "branch": "codex/feature-a",
            "head": "abc123",
        }
        rendered = MATRIX.render_slot_env(
            ["APP_PORT=82{port_offset}", "TEST_DB=app_{name}_{slot}", "CHECKOUT={path}"],
            context,
        )
        self.assertEqual(rendered["APP_PORT"], "82200")
        self.assertEqual(rendered["TEST_DB"], "app_feature-a_2")
        self.assertEqual(rendered["CHECKOUT"], "/tmp/repo-a")

    def test_rejects_unknown_template_fields(self) -> None:
        context = {field: "x" for field in MATRIX.SLOT_FIELDS}
        with self.assertRaisesRegex(ValueError, "unknown"):
            MATRIX.render_slot_env(["APP_PORT={unknown}"], context)

    def test_invalid_slot_template_creates_no_log_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            log_dir = root / "logs"
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Eval"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "eval@example.invalid"], check=True)
            (repo / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "chore: seed"], check=True)

            completed = subprocess.run(
                [
                    "python3", str(SCRIPT), "run", "--repo", str(repo),
                    "--worktree", str(repo), "--log-dir", str(log_dir),
                    "--slot-env", "APP_PORT={unknown}", "--", "true",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("invalid --slot-env field", completed.stderr)
            self.assertFalse(log_dir.exists())

    def test_portable_fixture_has_expected_branch_dirty_state_and_no_remote(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = PREPARE.prepare("portable-parallel", Path(temporary) / "repo")
            branch = subprocess.run(
                ["git", "-C", str(target), "branch", "--show-current"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            branches = subprocess.run(
                ["git", "-C", str(target), "branch", "--format=%(refname:short)"],
                capture_output=True, text=True, check=True,
            ).stdout.splitlines()
            status = subprocess.run(
                ["git", "-C", str(target), "status", "--porcelain"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            remotes = subprocess.run(
                ["git", "-C", str(target), "remote"], capture_output=True, text=True, check=True,
            ).stdout.strip()

            self.assertEqual(branch, "develop")
            self.assertIn("integration", branches)
            self.assertEqual(status, "M README.md")
            self.assertEqual(remotes, "")

    def test_default_log_directory_is_reported_complete_and_cleanup_owned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Eval"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "eval@example.invalid"], check=True)
            (repo / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "chore: seed"], check=True)
            worktrees = [root / "worktree-a", root / "worktree-b"]
            for index, worktree in enumerate(worktrees):
                subprocess.run(
                    ["git", "-C", str(repo), "worktree", "add", "-q", "-b", f"task/{index}", str(worktree), "HEAD"],
                    check=True,
                )

            completed = subprocess.run(
                [
                    "python3", str(SCRIPT), "run", "--repo", str(repo),
                    "--worktree", str(worktrees[0]), "--worktree", str(worktrees[1]),
                    "--max-parallel", "2", "--slot-env", "EVAL_SLOT={slot}", "--",
                    "python3", "-c", "import os; print(os.environ['EVAL_SLOT'])",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            match = re.search(r"^LOG_DIR (.+)$", completed.stdout, re.MULTILINE)
            self.assertIsNotNone(match)
            log_dir = Path(match.group(1))
            try:
                summary = json.loads((log_dir / "summary.json").read_text(encoding="utf-8"))
                self.assertEqual([item["exit"] for item in summary["results"]], [0, 0])
                self.assertEqual(
                    sorted(path.read_text(encoding="utf-8").strip() for path in log_dir.glob("*.log")),
                    ["0", "1"],
                )
            finally:
                shutil.rmtree(log_dir)
            self.assertFalse(log_dir.exists())


if __name__ == "__main__":
    unittest.main()
