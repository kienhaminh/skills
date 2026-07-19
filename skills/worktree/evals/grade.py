#!/usr/bin/env python3
"""Deterministically grade raw worktree benchmark responses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = SKILL_ROOT / "evals" / "evals.json"
DEFAULT_RUNS = SKILL_ROOT / "evals" / "runs"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def matches_group(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def grade_response(
    case: dict[str, Any], configuration: str, response: str, pass_threshold: int
) -> dict[str, Any]:
    checks = []
    for check in case["checks"]:
        groups = check["groups"]
        evidence = [matches_group(response, group) for group in groups]
        passed = all(evidence)
        checks.append(
            {
                "id": check["id"],
                "description": check["description"],
                "points": check["points"],
                "passed": passed,
                "groups_matched": evidence,
            }
        )
    score = sum(check["points"] for check in checks if check["passed"])
    maximum = sum(check["points"] for check in checks)
    return {
        "case_id": case["id"],
        "configuration": configuration,
        "score": score,
        "maximum": maximum,
        "passed": score >= pass_threshold,
        "checks": checks,
    }


def grade(spec_path: Path, runs_dir: Path) -> dict[str, Any]:
    spec = load_json(spec_path)
    reports = []
    for case in spec["cases"]:
        for configuration in ("with_skill", "baseline"):
            response_path = runs_dir / f"{case['id']}.{configuration}.md"
            if not response_path.is_file():
                reports.append(
                    {
                        "case_id": case["id"],
                        "configuration": configuration,
                        "score": 0,
                        "maximum": spec["maximum_per_case"],
                        "passed": False,
                        "error": f"missing response: {response_path}",
                        "checks": [],
                    }
                )
                continue
            response = response_path.read_text(encoding="utf-8")
            report = grade_response(case, configuration, response, spec["pass_threshold"])
            report["response_path"] = str(response_path)
            reports.append(report)

    configurations: dict[str, dict[str, Any]] = {}
    for configuration in ("with_skill", "baseline"):
        selected = [report for report in reports if report["configuration"] == configuration]
        total = sum(report["score"] for report in selected)
        maximum = sum(report["maximum"] for report in selected)
        configurations[configuration] = {
            "score": total,
            "maximum": maximum,
            "pass_count": sum(1 for report in selected if report["passed"]),
            "case_count": len(selected),
            "mean": round(total / len(selected), 2) if selected else 0,
        }

    delta = configurations["with_skill"]["score"] - configurations["baseline"]["score"]
    return {
        "version": 1,
        "skill": spec["skill"],
        "method": spec["method"],
        "pass_threshold": spec["pass_threshold"],
        "runs": reports,
        "summary": {"configurations": configurations, "skill_score_delta": delta},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = grade(args.spec.resolve(), args.runs_dir.resolve())
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["summary"]["configurations"]["with_skill"]["pass_count"] == len(report["runs"]) // 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
