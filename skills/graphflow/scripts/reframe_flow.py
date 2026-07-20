#!/usr/bin/env python3
"""Classify an existing flow and bind user approval to a reframe proposal."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


WORKFLOW_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CANONICAL_FIELDS = {
    "version", "workflow_id", "lifecycle", "objective", "constraints",
    "intent_baseline", "question_gate", "verification", "shared_memory", "integrity",
    "optional_work", "nodes",
}
APPROVAL_FIELDS = {"schema_version", "proposal_digest", "decision", "approved_by", "approved_at"}
REFRAME_FIELDS = {
    "objective", "non_goals", "requirements", "nodes", "dependencies", "scopes",
    "prototype_gate", "verification_oracles", "unknowns", "discarded_semantics",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def file_digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def source_file(source: Path) -> tuple[Path, str]:
    if source.is_dir():
        graph = source / "graph.json"
        if not graph.is_file():
            raise ValueError("directory source must contain graph.json; otherwise point to the flow definition file")
        return graph, "directory"
    if not source.is_file():
        raise ValueError("source must be a file or a workflow directory containing graph.json")
    return source, "file"


def validate_canonical(path: Path) -> tuple[bool, list[str]]:
    validator = Path(__file__).with_name("validate_graph.py")
    completed = subprocess.run(
        [sys.executable, str(validator), str(path), "--phase", "draft", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return False, [(completed.stdout + completed.stderr).strip() or "validator produced no report"]
    errors = report.get("errors", []) if isinstance(report, dict) else []
    return completed.returncode == 0, [str(value) for value in errors]


def candidate_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"source_keys": [], "objective_candidate": None, "node_count": None, "edge_count": None}
    objective = None
    for key in ("objective", "goal", "title", "name"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            objective = candidate.strip()[:300]
            break
        if isinstance(candidate, dict):
            statement = candidate.get("statement")
            if isinstance(statement, str) and statement.strip():
                objective = statement.strip()[:300]
                break
    nodes = next((value.get(key) for key in ("nodes", "steps", "tasks") if isinstance(value.get(key), list)), None)
    edges = next((value.get(key) for key in ("edges", "dependencies", "transitions") if isinstance(value.get(key), list)), None)
    return {
        "source_keys": sorted(str(key) for key in value),
        "objective_candidate": objective,
        "node_count": len(nodes) if isinstance(nodes, list) else None,
        "edge_count": len(edges) if isinstance(edges, list) else None,
    }


def inspect(source: Path, output: Path, requested_workflow_id: str | None) -> dict[str, Any]:
    definition, source_kind = source_file(source)
    if output.resolve() == definition.resolve():
        raise ValueError("output must not overwrite the source flow")
    parsed = load_json(definition)
    canonical_shape = isinstance(parsed, dict) and CANONICAL_FIELDS.issubset(parsed)
    valid, validation_errors = validate_canonical(definition) if canonical_shape else (False, [])
    if valid:
        classification = "canonical-graphflow-v3"
        workflow_id = parsed.get("workflow_id")
        action = "edit-canonical"
        confirmation_required = False
        status = "not_required"
    else:
        structured = isinstance(parsed, dict) and any(key in parsed for key in ("nodes", "steps", "tasks", "edges", "transitions"))
        classification = "noncanonical-structured" if structured else "opaque"
        workflow_id = requested_workflow_id
        action = "reframe-required"
        confirmation_required = True
        status = "awaiting_user_confirmation"
        if not isinstance(workflow_id, str) or not WORKFLOW_ID_RE.fullmatch(workflow_id):
            raise ValueError("noncanonical sources require --workflow-id in kebab-case")
    proposal = {
        "schema_version": 1,
        "source": {
            "path": str(definition.resolve()),
            "kind": source_kind,
            "digest": file_digest(definition),
        },
        "classification": classification,
        "canonical_validation": {"valid": valid, "errors": validation_errors},
        "proposed_action": action,
        "target": {
            "format": "graphflow-v3",
            "workflow_id": workflow_id,
            "preserve_source_until_cutover": True,
        },
        "candidate_summary": candidate_summary(parsed),
        "required_reframe_mapping": [] if valid else [
            "objective and non-goals",
            "atomic requirements and acceptance",
            "nodes and dependencies",
            "read/write/artifact/decision scopes",
            "prototype and verification oracles",
            "unknowns and discarded semantics",
        ],
        "reframe_mapping": None if valid else {
            "objective": None,
            "non_goals": [],
            "requirements": [],
            "nodes": [],
            "dependencies": [],
            "scopes": {},
            "prototype_gate": {},
            "verification_oracles": [],
            "unknowns": [],
            "discarded_semantics": [],
        },
        "confirmation": {
            "required": confirmation_required,
            "status": status,
            "instruction": None if valid else "Present this proposal and its digest to the user; do not convert or edit the source before explicit approval.",
        },
        "generated_at": now_utc(),
    }
    atomic_json(output, proposal)
    return {
        "classification": classification,
        "proposed_action": action,
        "confirmation_required": confirmation_required,
        "proposal": str(output.resolve()),
        "proposal_digest": file_digest(output),
    }


def verify_approval(proposal_path: Path, approval_path: Path) -> dict[str, Any]:
    proposal = load_json(proposal_path)
    approval = load_json(approval_path)
    if not isinstance(proposal, dict):
        raise ValueError("proposal must be valid JSON")
    if not isinstance(approval, dict) or set(approval) != APPROVAL_FIELDS:
        raise ValueError(f"approval must contain exactly {sorted(APPROVAL_FIELDS)!r}")
    confirmation = proposal.get("confirmation") if isinstance(proposal.get("confirmation"), dict) else {}
    if confirmation.get("required") is not True:
        raise ValueError("this canonical flow does not require reframe approval")
    mapping = proposal.get("reframe_mapping")
    if not isinstance(mapping, dict) or set(mapping) != REFRAME_FIELDS:
        raise ValueError("proposal reframe_mapping is incomplete")
    if not isinstance(mapping.get("objective"), str) or not mapping["objective"].strip():
        raise ValueError("proposal reframe_mapping.objective must be resolved")
    for field in ("non_goals", "dependencies", "verification_oracles", "unknowns", "discarded_semantics"):
        if not isinstance(mapping.get(field), list):
            raise ValueError(f"proposal reframe_mapping.{field} must be a list")
    for field in ("requirements", "nodes", "verification_oracles"):
        if not mapping.get(field):
            raise ValueError(f"proposal reframe_mapping.{field} must not be empty")
    for field in ("scopes", "prototype_gate"):
        if not isinstance(mapping.get(field), dict) or not mapping[field]:
            raise ValueError(f"proposal reframe_mapping.{field} must be a non-empty object")
    expected_digest = file_digest(proposal_path)
    if approval.get("schema_version") != 1 or approval.get("proposal_digest") != expected_digest:
        raise ValueError("approval does not match the current proposal digest")
    if approval.get("decision") != "approved" or approval.get("approved_by") != "user":
        raise ValueError("reframe requires an explicit user approval")
    if not isinstance(approval.get("approved_at"), str) or not approval["approved_at"].strip():
        raise ValueError("approved_at must be a non-empty timestamp")
    return {"approved": True, "proposal_digest": expected_digest, "workflow_id": (proposal.get("target") or {}).get("workflow_id")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("source", type=Path)
    inspect_parser.add_argument("--output", type=Path, required=True)
    inspect_parser.add_argument("--workflow-id")
    verify_parser = subparsers.add_parser("verify-approval")
    verify_parser.add_argument("proposal", type=Path)
    verify_parser.add_argument("approval", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            result = inspect(args.source.resolve(), args.output.resolve(), args.workflow_id)
        else:
            result = verify_approval(args.proposal.resolve(), args.approval.resolve())
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
