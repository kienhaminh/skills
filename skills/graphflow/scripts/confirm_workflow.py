#!/usr/bin/env python3
"""Record a digest-bound response to one Graphflow confirmation request."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from executor_common import atomic_json, load_executor, load_json, now_utc
import delivery_broker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workflow_dir", type=Path)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--decision", choices=("approved", "rejected"), required=True)
    parser.add_argument("--answer", required=True)
    args = parser.parse_args()
    workflow_dir = args.workflow_dir.resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.request_id):
        parser.error("request-id must be a stable path-safe identifier")
    request_path = workflow_dir / "runtime" / "requests" / f"{args.request_id}.json"
    try:
        request = load_json(request_path, "confirmation request")
        if not isinstance(request, dict) or request.get("request_id") != args.request_id:
            raise ValueError("request identity mismatch")
        if request.get("digest") != args.digest:
            raise ValueError("request digest mismatch; inspect the current request before responding")
        if request.get("status") != "pending":
            raise ValueError("request is no longer pending")
        triage = request.get("triage") if isinstance(request.get("triage"), dict) else {}
        surface = json.dumps(
            {
                "question": request.get("question"),
                "alternatives": request.get("alternatives"),
                "risks": request.get("risks"),
                "triage": triage,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if request.get("digest") != "sha256:" + hashlib.sha256(surface).hexdigest():
            raise ValueError("stored request digest does not match its current decision surface")
        capabilities = triage.get("authority_capabilities", [])
        if args.decision == "approved" and capabilities:
            runtime_path = workflow_dir / "runtime.json"
            runtime = load_json(runtime_path, "runtime authority")
            if not isinstance(runtime, dict):
                raise ValueError("runtime must be an object")
            grant = {
                "capabilities": capabilities,
                "request_id": args.request_id,
                "request_digest": args.digest,
                "granted_at": now_utc(),
            }
            if request.get("broker") == "delivery":
                delivery = delivery_broker.validate_config(runtime.get("delivery"), str(runtime.get("workflow_id")))
                if capabilities != delivery.get("required_capabilities") or triage.get("delivery_manifest_digest") is None:
                    raise ValueError("delivery request exceeds or does not bind its declared Ship contract")
                delivery["grant"] = grant
                runtime["delivery"] = delivery
            else:
                node_id = request.get("node_id")
                if not isinstance(node_id, str):
                    raise ValueError("authority request is missing node identity")
                _, _, spec, _ = load_executor(workflow_dir, node_id)
                if not set(capabilities).issubset(set(spec.get("requires_authority", []))):
                    raise ValueError("authority request exceeds the executor's declared capabilities")
                grants = runtime.setdefault("authority_grants", {})
                if not isinstance(grants, dict):
                    raise ValueError("runtime.authority_grants must be an object")
                grants[node_id] = grant
            atomic_json(runtime_path, runtime)
        request["status"] = args.decision
        request["response"] = {"answer": args.answer, "recorded_at": now_utc()}
        atomic_json(request_path, request)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({"request_id": args.request_id, "status": args.decision, "digest": args.digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
