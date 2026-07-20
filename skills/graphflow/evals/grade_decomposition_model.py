#!/usr/bin/env python3
"""Grade a small-model Graphflow runtime-decomposition decision sample."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import decomposition_broker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    value = json.loads(args.result.read_text(encoding="utf-8"))
    cases = {item.get("case_id"): item for item in value.get("cases", []) if isinstance(item, dict)}
    errors: list[str] = []
    if set(cases) != {"structural-execute", "semantic-ambiguity", "integration-redesign"}:
        errors.append("case set is incomplete or duplicated")
    for case_id in ("semantic-ambiguity", "integration-redesign"):
        case = cases.get(case_id, {})
        if case.get("action") != "rebase" or case.get("proposal") is not None:
            errors.append(f"{case_id} must rebase without a proposal")
    structural = cases.get("structural-execute", {})
    proposal = structural.get("proposal")
    if structural.get("action") != "decompose" or not isinstance(proposal, dict):
        errors.append("structural-execute must provide a decomposition")
    else:
        graph = {
            "nodes": [{
                "id": "B", "kind": "execute", "scope": {
                    "read": ["src"], "write": ["src/search.ts"], "artifacts": [],
                    "decisions": ["search-sort"], "forbidden": [".env"],
                },
                "consumes": ["sort-contract"],
                "outputs": [{"id": "search-behavior", "description": "Implemented search sorting.", "artifact": "src/search.ts"}],
                "acceptance": ["Implemented search sorting."],
                "budget": {"tokens": 1000},
            }],
        }
        spec = {"type": "agent", "acceptance_checks": ["CHK-B"]}
        plan = {"checks": [{"id": "CHK-B"}]}
        try:
            decomposition_broker.validate_proposal(graph, graph["nodes"][0], spec, proposal, plan)
        except ValueError as error:
            errors.append(f"structural proposal invalid: {error}")
    print(json.dumps({"passed": not errors, "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
