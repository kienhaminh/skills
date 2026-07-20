#!/usr/bin/env python3
"""Materialize an isolated ship evaluation repository from a fixture template."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def run_git(target: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=target, check=True, capture_output=True, text=True)


def prepare(case: str, target: Path, local_remote: bool = False) -> Path:
    source = FIXTURES / case
    baseline = source / "baseline"
    working = source / "working"

    if not baseline.is_dir() or not working.is_dir():
        raise ValueError(f"unknown or incomplete fixture: {case}")
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")

    shutil.copytree(baseline, target)
    run_git(target, "init", "-b", "main")
    run_git(target, "config", "user.name", "Ship Eval")
    run_git(target, "config", "user.email", "ship-eval@example.invalid")
    run_git(target, "add", "--all")
    run_git(target, "commit", "-m", "chore: seed ship evaluation")
    if local_remote:
        remote = target.parent / f"{target.name}.git"
        if remote.exists():
            raise FileExistsError(f"local remote already exists: {remote}")
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        run_git(target, "remote", "add", "sandbox", str(remote))
        run_git(target, "push", "-q", "sandbox", "main")
        run_git(target, "switch", "-q", "-c", "task/readme-port")
    shutil.copytree(working, target, dirs_exist_ok=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=sorted(path.name for path in FIXTURES.iterdir() if path.is_dir()))
    parser.add_argument("target", type=Path)
    parser.add_argument("--local-remote", action="store_true")
    args = parser.parse_args()
    prepared = prepare(args.case, args.target.resolve(), args.local_remote)
    print(prepared)


if __name__ == "__main__":
    main()
