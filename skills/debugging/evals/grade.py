#!/usr/bin/env python3
"""Deterministically grade small-model debugging-skill responses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_SPEC = ROOT / "complex" / "evals.json"
DEFAULT_RUNS = ROOT / "complex" / "runs"


def matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def grade_check(text: str, check: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    if "forbidden" in check:
        hits = [pattern for pattern in check["forbidden"] if re.search(pattern, text, flags=re.IGNORECASE)]
        return not hits, {"forbidden_hits": hits}
    matched = [matches(text, group) for group in check["groups"]]
    return all(matched), {"groups_matched": matched}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    max_output_words = spec.get("max_output_words")
    reports = []
    for model in spec["models"]:
        profile = model["reasoning_effort"]
        for case in spec["cases"]:
            for configuration in ("with_skill", "baseline"):
                path = args.runs_dir / f"{case['id']}.{profile}.{configuration}.md"
                text = path.read_text(encoding="utf-8") if path.is_file() else ""
                try:
                    response_path = path.relative_to(ROOT).as_posix()
                except ValueError:
                    response_path = path.as_posix()
                checks = []
                for check in case["checks"]:
                    passed, evidence = grade_check(text, check)
                    checks.append({**check, "passed": passed, **evidence})
                score = sum(check["points"] for check in checks if check["passed"])
                maximum = sum(check["points"] for check in checks)
                word_count = len(text.split())
                within_word_limit = max_output_words is None or word_count <= max_output_words
                reports.append({
                    "case_id": case["id"],
                    "model": model["model"],
                    "reasoning_effort": profile,
                    "configuration": configuration,
                    "score": score,
                    "maximum": maximum,
                    "passed": score >= spec["pass_threshold"] and within_word_limit,
                    "quality_passed": score >= spec["pass_threshold"],
                    "word_count": word_count,
                    "within_word_limit": within_word_limit,
                    "failed_checks": [check["id"] for check in checks if not check["passed"]],
                    "response_path": response_path,
                })

    summary = {}
    for profile in [model["reasoning_effort"] for model in spec["models"]]:
        summary[profile] = {}
        for configuration in ("with_skill", "baseline"):
            selected = [r for r in reports if r["reasoning_effort"] == profile and r["configuration"] == configuration]
            summary[profile][configuration] = {
                "score": sum(r["score"] for r in selected),
                "maximum": sum(r["maximum"] for r in selected),
                "pass_count": sum(1 for r in selected if r["passed"]),
                "quality_pass_count": sum(1 for r in selected if r["quality_passed"]),
                "compact_count": sum(1 for r in selected if r["within_word_limit"]),
                "average_words": round(sum(r["word_count"] for r in selected) / len(selected), 1) if selected else 0,
                "word_limit": max_output_words,
                "case_count": len(selected),
            }
        summary[profile]["skill_score_delta"] = summary[profile]["with_skill"]["score"] - summary[profile]["baseline"]["score"]

    result = {"version": 1, "skill": spec["skill"], "method": spec["method"], "runs": reports, "summary": summary}
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
