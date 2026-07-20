#!/usr/bin/env python3
"""Materialize the portable worktree planning fixture as an isolated Git repository."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def prepare(case: str, target: Path) -> Path:
    source = FIXTURES / case
    if not source.is_dir():
        raise ValueError(f"unknown fixture: {case}")
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")
    shutil.copytree(source, target)
    subprocess.run(["git", "init", "-q", "-b", "develop", str(target)], check=True)
    for key, value in (("user.name", "Worktree Eval"), ("user.email", "eval@example.invalid")):
        subprocess.run(["git", "-C", str(target), "config", key, value], check=True)
    subprocess.run(["git", "-C", str(target), "add", "--all"], check=True)
    subprocess.run(["git", "-C", str(target), "commit", "-qm", "chore: seed fixture"], check=True)
    subprocess.run(["git", "-C", str(target), "branch", "integration"], check=True)
    readme = target / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nLocal operator note.\n", encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=sorted(path.name for path in FIXTURES.iterdir() if path.is_dir()))
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    print(prepare(args.case, args.target.resolve()))


if __name__ == "__main__":
    main()
