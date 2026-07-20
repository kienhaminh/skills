from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from skills.ship.evals.prepare_fixture import prepare


def run(target: Path, *command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=target, capture_output=True, text=True)


class PrepareFixtureTests(unittest.TestCase):
    def test_cases_have_expected_gate_and_repository_state(self) -> None:
        expectations = {
            "happy-path-close-plan": 0,
            "red-gate-halts": 1,
            "no-plan-small-change": 0,
        }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for case, expected_test_code in expectations.items():
                with self.subTest(case=case):
                    target = prepare(case, root / case)
                    status = run(target, "git", "status", "--porcelain")
                    remotes = run(target, "git", "remote")
                    tests = run(target, "npm", "test")

                    self.assertEqual(status.returncode, 0)
                    self.assertTrue(status.stdout.strip())
                    self.assertEqual(remotes.stdout.strip(), "")
                    self.assertEqual(tests.returncode, expected_test_code)

    def test_push_fixture_has_proved_local_remote_and_task_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = prepare("no-plan-small-change", Path(temporary) / "push-only", local_remote=True)
            branch = run(target, "git", "branch", "--show-current")
            remotes = run(target, "git", "remote")
            remote_main = run(target, "git", "ls-remote", "sandbox", "refs/heads/main")

            self.assertEqual(branch.stdout.strip(), "task/readme-port")
            self.assertEqual(remotes.stdout.strip(), "sandbox")
            self.assertTrue(remote_main.stdout.strip())


if __name__ == "__main__":
    unittest.main()
