#!/usr/bin/env python3
"""Regression tests for deterministic Graphflow eval grading."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("graphflow_grade", ROOT / "evals" / "grade.py")
assert SPEC and SPEC.loader
GRADE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADE)


class GradeTests(unittest.TestCase):
    def test_validation_commands_bind_repo_root_to_artifact_not_caller_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory).resolve()
            commands: list[list[str]] = []

            def capture(command: list[str]) -> tuple[int, str]:
                commands.append(command)
                return 1, "expected incomplete fixture"

            with mock.patch.object(GRADE, "run", side_effect=capture):
                GRADE.grade(artifact)

            memory = next(command for command in commands if str(GRADE.MEMORY) in command and "validate" in command)
            integrity = next(command for command in commands if str(GRADE.INTEGRITY) in command and "validate" in command)
            self.assertEqual(memory[memory.index("--repo-root") + 1], str(artifact))
            self.assertEqual(integrity[integrity.index("--repo-root") + 1], str(artifact))


if __name__ == "__main__":
    unittest.main()
