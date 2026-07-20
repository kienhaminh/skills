#!/usr/bin/env python3
"""Apply independently-reviewed, contract-equivalent runtime decomposition."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import evidence_runner
import memory_state
import question_gate
import workspace_manager
from executor_common import atomic_bytes, atomic_json, canonical_graph_digest, fsync_directory, inside, json_digest, load_executor, load_json, now_utc, sha256


POLICY = "structural-decomposition-v1"
CONFIG_FIELDS = {
    "schema_version", "policy", "status", "reviewer_model", "reviewer_reasoning_effort",
    "active_node", "revision", "last_proof", "failure", "updated_at",
}
CHILD_FIELDS = {
    "key", "title", "outcome", "operations", "methods", "skills", "depends_on",
    "scope", "consumes", "outputs", "acceptance", "acceptance_checks", "budget_tokens",
}
PROPOSAL_FIELDS = {
    "schema_version", "contract_change", "reason_class", "reason", "measure", "terminal_child", "children",
}
KEY_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
BOUND_POLICY = "ranking-function-v1"
JOURNAL_POLICY = "decomposition-write-ahead-v1"
REVIEW_CACHE_POLICY = "decomposition-review-cache-v1"
REVIEW_POLICY = "question-challenge-v1"
BACKUP_MANIFEST_POLICY = "merkle-backup-v1"
REVIEW_PROMPT_POLICY = (
    "Independently challenge this structural-only Graphflow decomposition using Rumsfeld Matrix, Value of Information, Reversibility, and Premortem. "
    "Return only one question-review JSON object with exactly the Graphflow question-review fields. Cover exactly misread-intent, hidden-dependency, and oracle-gap. "
    "Use status passed unless a finding is pivotal_open; do not accept scope expansion, acceptance/oracle changes, hidden output ancestry, or budget laundering."
)
CORE_FILES = (
    "graph.json", "question-review.json", "integrity/verification-plan.json", "integrity/lock.json",
    "memory/state.json", "memory/events.jsonl", "runtime/workspaces.json",
)
REVISION_ARTIFACTS = ("proof.json", "proposal.json", "review.json")


def default_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy": POLICY,
        "status": "idle",
        "reviewer_model": "gpt-5.6-terra",
        "reviewer_reasoning_effort": "low",
        "active_node": None,
        "revision": 0,
        "last_proof": None,
        "failure": None,
        "updated_at": None,
    }


def validate_config(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != CONFIG_FIELDS:
        raise ValueError(f"runtime.decomposition must contain exactly {sorted(CONFIG_FIELDS)!r}")
    if value.get("schema_version") != 1 or value.get("policy") != POLICY:
        raise ValueError("runtime.decomposition has an unsupported schema or policy")
    if value.get("status") not in {"idle", "reviewing", "waiting_rebase", "applied", "blocked"}:
        raise ValueError("runtime.decomposition status is invalid")
    if value.get("reviewer_model") is not None and (not isinstance(value.get("reviewer_model"), str) or not value["reviewer_model"]):
        raise ValueError("runtime.decomposition.reviewer_model must be null or non-empty")
    if value.get("reviewer_reasoning_effort") not in {"low", "medium"}:
        raise ValueError("runtime.decomposition reviewer effort must be low or medium")
    if not isinstance(value.get("revision"), int) or isinstance(value.get("revision"), bool) or value["revision"] < 0:
        raise ValueError("runtime.decomposition.revision must be non-negative")
    for field in ("active_node", "last_proof", "failure"):
        if value.get(field) is not None and not isinstance(value.get(field), str):
            raise ValueError(f"runtime.decomposition.{field} must be null or a string")
    return dict(value)


def string_list(value: Any, *, nonempty: bool = False) -> bool:
    return isinstance(value, list) and (not nonempty or bool(value)) and all(isinstance(item, str) and bool(item) for item in value) and len(value) == len(set(value))


def path_overlap(left: str, right: str) -> bool:
    a = PurePosixPath(left).parts
    b = PurePosixPath(right).parts
    return a == b or a == b[: len(a)] or b == a[: len(b)]


def path_within(path: str, root: str) -> bool:
    value = PurePosixPath(path).parts
    boundary = PurePosixPath(root).parts
    return boundary == value[: len(boundary)]


def exact_partition(parent: list[str], child_values: list[list[str]], label: str) -> None:
    flattened = [value for values in child_values for value in values]
    if set(flattened) != set(parent) or len(flattened) != len(set(flattened)):
        raise ValueError(f"decomposition children must exactly partition parent {label}")
    for index, left in enumerate(flattened):
        for right in flattened[index + 1 :]:
            if path_overlap(left, right):
                raise ValueError(f"decomposition {label} paths overlap: {left!r} and {right!r}")


def ancestors(key: str, dependencies: dict[str, list[str]]) -> set[str]:
    found: set[str] = set()
    stack = list(dependencies.get(key, []))
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        stack.extend(dependencies.get(current, []))
    return found


def validate_proposal(graph: dict[str, Any], node: dict[str, Any], spec: dict[str, Any], proposal: Any, plan: dict[str, Any]) -> dict[str, Any]:
    if node.get("kind") != "execute" or spec.get("type") != "agent":
        raise ValueError("automatic decomposition is limited to agent execute nodes; integrate/verify/command changes require rebase")
    if not isinstance(proposal, dict) or set(proposal) != PROPOSAL_FIELDS:
        raise ValueError(f"decomposition must contain exactly {sorted(PROPOSAL_FIELDS)!r}")
    if proposal.get("schema_version") != 1 or proposal.get("contract_change") != "structural":
        raise ValueError("automatic decomposition accepts only structural schema-version-1 proposals")
    if proposal.get("reason_class") not in {"complexity", "context", "hidden_dependency"} or not isinstance(proposal.get("reason"), str) or not proposal["reason"].strip():
        raise ValueError("decomposition requires a controlled reason class and non-empty reason")
    children = proposal.get("children")
    if not isinstance(children, list) or len(children) < 2 or any(not isinstance(child, dict) or set(child) != CHILD_FIELDS for child in children):
        raise ValueError(f"decomposition requires at least two children with exactly {sorted(CHILD_FIELDS)!r}")
    keys = [child.get("key") for child in children]
    if any(not isinstance(key, str) or not KEY_RE.fullmatch(key) for key in keys) or len(keys) != len(set(keys)):
        raise ValueError("decomposition child keys must be unique kebab-case identifiers")
    terminal = proposal.get("terminal_child")
    if terminal not in keys:
        raise ValueError("decomposition terminal_child must identify one proposed child")

    measure = proposal.get("measure")
    if not isinstance(measure, dict) or set(measure) != {"name", "parent", "children"} or not isinstance(measure.get("name"), str) or not measure["name"]:
        raise ValueError("decomposition measure must contain exactly name, parent, and children")
    parent_measure = measure.get("parent")
    measured = measure.get("children")
    if not isinstance(parent_measure, int) or isinstance(parent_measure, bool) or parent_measure < 2 or not isinstance(measured, list):
        raise ValueError("decomposition measure parent must be an integer >= 2")
    measured_map = {item.get("key"): item.get("value") for item in measured if isinstance(item, dict) and set(item) == {"key", "value"}}
    if set(measured_map) != set(keys) or len(measured_map) != len(measured) or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 or value >= parent_measure for value in measured_map.values()):
        raise ValueError("every child needs one positive complexity measure strictly below its parent")
    inherited_bound = node.get("decomposition_bound")
    if inherited_bound is not None:
        if (
            not isinstance(inherited_bound, dict)
            or inherited_bound.get("policy") != BOUND_POLICY
            or not isinstance(inherited_bound.get("name"), str)
            or not isinstance(inherited_bound.get("value"), int)
        ):
            raise ValueError("node decomposition_bound is invalid")
        if measure["name"] != inherited_bound["name"] or parent_measure != inherited_bound["value"]:
            raise ValueError("recursive decomposition measure must continue from the node's inherited bound")

    dependencies: dict[str, list[str]] = {}
    for child in children:
        for field in ("operations", "methods", "skills", "depends_on", "consumes", "acceptance", "acceptance_checks"):
            if not string_list(child.get(field), nonempty=field in {"operations", "methods", "acceptance", "acceptance_checks"}):
                raise ValueError(f"decomposition child {child['key']}.{field} must be a unique string list")
        if len(child["methods"]) > 3 or any(key not in keys or key == child["key"] for key in child["depends_on"]):
            raise ValueError(f"decomposition child {child['key']} has invalid methods or dependencies")
        dependencies[child["key"]] = list(child["depends_on"])
        scope = child.get("scope")
        if not isinstance(scope, dict) or set(scope) != {"read", "write", "artifacts", "decisions", "forbidden"} or any(not string_list(scope.get(field)) for field in scope):
            raise ValueError(f"decomposition child {child['key']} scope is invalid")
        if not isinstance(child.get("outputs"), list) or any(not isinstance(output, dict) or set(output) != {"id", "description", "artifact"} for output in child["outputs"]):
            raise ValueError(f"decomposition child {child['key']} outputs are invalid")
        if not isinstance(child.get("budget_tokens"), int) or isinstance(child.get("budget_tokens"), bool) or child["budget_tokens"] <= 0:
            raise ValueError(f"decomposition child {child['key']} budget must be positive")
    if any(key in ancestors(key, dependencies) for key in keys):
        raise ValueError("decomposition child dependency graph contains a cycle")
    terminal_ancestors = ancestors(str(terminal), dependencies)
    if set(keys) - {terminal} - terminal_ancestors:
        raise ValueError("every support child must be an ancestor of terminal_child")

    parent_scope = node.get("scope") if isinstance(node.get("scope"), dict) else {}
    exact_partition(list(parent_scope.get("write", [])), [child["scope"]["write"] for child in children], "write scope")
    exact_partition(list(parent_scope.get("artifacts", [])), [child["scope"]["artifacts"] for child in children], "artifact scope")
    exact_partition(list(parent_scope.get("decisions", [])), [child["scope"]["decisions"] for child in children], "decision scope")
    readable = set(parent_scope.get("read", [])) | set(parent_scope.get("write", [])) | set(parent_scope.get("artifacts", []))
    forbidden = set(parent_scope.get("forbidden", []))
    for child in children:
        if any(not any(path_within(path, root) for root in readable) for path in child["scope"]["read"]):
            raise ValueError(f"decomposition child {child['key']} expands parent read scope")
        if not forbidden.issubset(set(child["scope"]["forbidden"])):
            raise ValueError(f"decomposition child {child['key']} weakens parent forbidden scope")

    terminal_value = next(child for child in children if child["key"] == terminal)
    if terminal_value["acceptance"] != node.get("acceptance", []):
        raise ValueError("terminal_child must preserve the parent's acceptance text exactly")
    if terminal_value["outputs"] != node.get("outputs", []):
        raise ValueError("terminal_child must preserve every original output exactly")
    support_outputs = [output for child in children if child["key"] != terminal for output in child["outputs"]]
    support_ids = [output.get("id") for output in support_outputs]
    existing_ids = {output.get("id") for value in graph.get("nodes", []) if isinstance(value, dict) and value.get("id") != node.get("id") for output in value.get("outputs", []) if isinstance(output, dict)}
    if any(not isinstance(value, str) or not value or value in existing_ids for value in support_ids) or len(support_ids) != len(set(support_ids)):
        raise ValueError("support child outputs must use new unique IDs")
    if not set(support_ids).issubset(set(terminal_value["consumes"])):
        raise ValueError("terminal_child must consume every support child output")
    original_consumes = set(node.get("consumes", []))
    produced_by = {output["id"]: child["key"] for child in children for output in child["outputs"] if isinstance(output.get("id"), str)}
    for child in children:
        allowed = original_consumes | {output for output, producer in produced_by.items() if producer in ancestors(child["key"], dependencies)}
        if not set(child["consumes"]).issubset(allowed):
            raise ValueError(f"decomposition child {child['key']} consumes a non-ancestral output")

    parent_budget = node.get("budget", {}).get("tokens") if isinstance(node.get("budget"), dict) else None
    if not isinstance(parent_budget, int) or sum(child["budget_tokens"] for child in children) + 1 > parent_budget:
        raise ValueError("child budgets plus one coordination token must not exceed the parent budget")
    plan_checks = {check.get("id") for check in plan.get("checks", []) if isinstance(check, dict)}
    parent_checks = set(spec.get("acceptance_checks", []))
    proposed_checks = {check for child in children for check in child["acceptance_checks"]}
    if not proposed_checks.issubset(plan_checks) or proposed_checks != parent_checks:
        raise ValueError("children must collectively preserve exactly the parent's existing locked acceptance checks")
    return proposal


def child_id(parent_id: str, key: str) -> str:
    return f"{parent_id}.{key}"


def child_prompt(parent_prompt: str, parent: dict[str, Any], child: dict[str, Any], proposal_digest: str) -> str:
    contract = {
        "outcome": child["outcome"],
        "operations": child["operations"],
        "methods": child["methods"],
        "skills": child["skills"],
        "scope": child["scope"],
        "consumes": child["consumes"],
        "outputs": child["outputs"],
        "acceptance": child["acceptance"],
        "acceptance_checks": child["acceptance_checks"],
        "budget_tokens": child["budget_tokens"],
    }
    return (
        f"Structural child of node {parent['id']}; decomposition {proposal_digest}.\n"
        "The parent objective, acceptance, authority, prototype, and verification oracle are immutable.\n"
        "Complete only this child contract and stop on scope insufficiency:\n"
        + json.dumps(contract, indent=2, sort_keys=True)
        + "\n\nOriginal bounded node context:\n"
        + parent_prompt.strip()
        + "\n"
    )


def build_candidate(workflow_dir: Path, node_id: str, proposal: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    graph = load_json(workflow_dir / "graph.json", "graph")
    plan = load_json(workflow_dir / "integrity" / "verification-plan.json", "verification plan")
    nodes = {str(node.get("id")): node for node in graph.get("nodes", []) if isinstance(node, dict)}
    parent = nodes.get(node_id)
    if parent is None:
        raise ValueError(f"unknown decomposition node {node_id}")
    _, _, parent_spec, _ = load_executor(workflow_dir, node_id)
    validate_proposal(graph, parent, parent_spec, proposal, plan)
    original_dependencies = list(parent.get("depends_on", []))
    original_parent = parent.get("parent")
    original_isolation = parent.get("isolation")
    proposal_digest = json_digest(proposal)
    terminal_key = str(proposal["terminal_child"])
    terminal_id = child_id(node_id, terminal_key)
    id_by_key = {child["key"]: child_id(node_id, child["key"]) for child in proposal["children"]}
    parent_prompt_path = workflow_dir / str(parent_spec.get("prompt"))
    parent_prompt = parent_prompt_path.read_text(encoding="utf-8")
    parent_contract = workspace_manager.workspace_contract(parent_spec)
    child_nodes: list[dict[str, Any]] = []
    created_dirs: dict[str, str] = {}

    for child in proposal["children"]:
        new_id = id_by_key[child["key"]]
        directory = workflow_dir / "nodes" / new_id
        if directory.exists():
            raise ValueError(f"decomposition target already exists: nodes/{new_id}")
        directory.mkdir(parents=True)
        prompt_path = directory / "prompt.md"
        prompt_path.write_text(child_prompt(parent_prompt, parent, child, proposal_digest), encoding="utf-8")
        is_terminal = child["key"] == terminal_key
        if is_terminal:
            workspace = dict(parent_contract)
        else:
            workspace = dict(parent_contract)
            workspace["ref"] = f"{parent_contract['ref']}-{child['key']}"
        resources = [
            dict(resource)
            for resource in parent_spec.get("resources", [])
            if resource.get("path") != parent_spec.get("prompt")
        ]
        relative_prompt = f"nodes/{new_id}/prompt.md"
        resources.append({"path": relative_prompt, "digest": sha256(prompt_path)})
        spec = {
            **parent_spec,
            "node_id": new_id,
            "workspace": workspace,
            "idempotency_key": f"{parent_spec['idempotency_key']}:{new_id}:{proposal_digest.split(':', 1)[1][:12]}",
            "acceptance_checks": child["acceptance_checks"],
            "resources": resources,
            "prompt": relative_prompt,
        }
        spec_path = directory / "executor.json"
        atomic_json(spec_path, spec)
        internal_dependencies = [id_by_key[key] for key in child["depends_on"]]
        child_nodes.append({
            "id": new_id,
            "title": child["title"],
            "kind": "execute",
            "executor": {
                "schema_version": 1,
                "type": "agent",
                "spec": f"nodes/{new_id}/executor.json",
                "digest": sha256(spec_path),
                "result": f"runtime/results/{new_id}.json",
            },
            "operations": child["operations"],
            "methods": child["methods"],
            "status": "pending",
            "isolation": original_isolation,
            "parent": node_id,
            "depends_on": list(dict.fromkeys([*original_dependencies, *internal_dependencies])),
            "skills": child["skills"],
            "covers": list(parent.get("covers", [])) if is_terminal else [],
            "scope": child["scope"],
            "consumes": child["consumes"],
            "outputs": child["outputs"],
            "acceptance": child["acceptance"],
            "decomposition_bound": {
                "policy": BOUND_POLICY,
                "name": proposal["measure"]["name"],
                "value": next(item["value"] for item in proposal["measure"]["children"] if item["key"] == child["key"]),
                "source_proposal": proposal_digest,
            },
            "budget": {"tokens": child["budget_tokens"]},
            "retry": {"attempts": 0, "max_attempts": 2, "last_failure_class": None},
            "runtime": {
                "agent": None,
                "model": parent_spec.get("model"),
                "reasoning_effort": parent_spec.get("reasoning_effort"),
                "routing_reason": f"Runtime structural decomposition of {node_id}; contract digest {proposal_digest}.",
                "started_at": None,
                "updated_at": None,
                "completed_at": None,
                "heartbeat_at": None,
                "summary": None,
                "blocker": None,
                "tokens_used": 0,
            },
        })
        created_dirs[new_id] = str(directory)

    parent.update(
        title=f"Expand: {parent.get('title')}",
        kind="expand",
        executor=None,
        operations=["decomposition"],
        methods=["MECE", "Reversibility", "YAGNI"],
        status="expanded",
        isolation="coordinator",
        parent=original_parent,
        skills=[],
        covers=[],
        scope={
            "read": list(parent.get("scope", {}).get("read", [])),
            "write": [], "artifacts": [], "decisions": [],
            "forbidden": list(parent.get("scope", {}).get("forbidden", [])),
        },
        consumes=[], outputs=[],
        acceptance=["Children preserve the original contract and form a finite MECE partition."],
        budget={"tokens": 1},
    )
    parent_runtime = parent.setdefault("runtime", {})
    parent_runtime.update(summary=f"Structurally decomposed into {', '.join(id_by_key.values())}.", completed_at=now_utc(), updated_at=now_utc(), blocker=None)
    for value in graph.get("nodes", []):
        if not isinstance(value, dict) or value.get("id") == node_id:
            continue
        dependencies = value.get("depends_on") if isinstance(value.get("depends_on"), list) else []
        value["depends_on"] = [terminal_id if dependency == node_id else dependency for dependency in dependencies]
    graph["nodes"].extend(child_nodes)
    graph.setdefault("lifecycle", {})["status"] = "active"
    graph["verification"] = {"outcome": "pending", "claims": []}
    graph["question_gate"]["status"] = "clear"
    graph["question_gate"]["unresolved_pivotal"] = []
    graph["question_gate"]["review"] = {
        "status": "required", "artifact": "question-review.json", "digest": None, "graph_digest": None, "reviewer_id": None,
    }
    graph["integrity"].update(status="proposed", plan_digest=None, runner_digest=None)
    atomic_json(workflow_dir / "graph.json", graph)

    duties = plan.get("separation_of_duties") if isinstance(plan.get("separation_of_duties"), dict) else {}
    producers = duties.get("producer_nodes") if isinstance(duties.get("producer_nodes"), list) else []
    if node_id in producers:
        replacement = [value for value in id_by_key.values()]
        duties["producer_nodes"] = [item for producer in producers for item in (replacement if producer == node_id else [producer])]
    atomic_json(workflow_dir / "integrity" / "verification-plan.json", plan)
    atomic_json(workflow_dir / "integrity" / "lock.json", {
        "schema_version": 1, "workflow_id": graph.get("workflow_id"), "status": "template",
        "plan_digest": None, "runner_digest": None, "contract_digest": None, "locked_at": None,
    })
    reviews = workflow_dir / "integrity" / "reviews"
    if reviews.is_dir():
        shutil.rmtree(reviews)
    reviews.mkdir(parents=True, exist_ok=True)
    workspace_manager.rebind(workflow_dir, {node_id: terminal_id})
    return graph, created_dirs


def review_prompt(graph: dict[str, Any], proposal: dict[str, Any], plan: dict[str, Any], reviewer_id: str) -> str:
    surface = {
        "objective": graph.get("objective"),
        "non_goals": graph.get("non_goals"),
        "intent_baseline": graph.get("intent_baseline"),
        "nodes": [
            {
                "id": node.get("id"), "kind": node.get("kind"), "operations": node.get("operations"),
                "depends_on": node.get("depends_on"), "covers": node.get("covers"), "scope": node.get("scope"),
                "consumes": node.get("consumes"), "outputs": node.get("outputs"), "acceptance": node.get("acceptance"),
            }
            for node in graph.get("nodes", []) if isinstance(node, dict)
        ],
        "verification_plan": plan,
        "decomposition": proposal,
    }
    return (
        REVIEW_PROMPT_POLICY + " "
        f"Set workflow_id={graph.get('workflow_id')!r}, graph_digest={question_gate.question_surface_digest(graph)!r}, reviewer.agent_id={reviewer_id!r}, "
        "reviewer.model_class='small', reviewer.independent=true, reviewer.context_policy='fresh-artifacts-only', methods exactly ['Rumsfeld Matrix','Value of Information','Reversibility','Premortem'], and a non-empty reviewed_at timestamp.\n\n"
        + json.dumps(surface, sort_keys=True)
    )


def review_cache_key(
    graph: dict[str, Any], proposal: dict[str, Any], plan: dict[str, Any], config: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    identity = {
        "schema_version": 1,
        "policy": REVIEW_CACHE_POLICY,
        "graph_digest": canonical_graph_digest(graph),
        "review_surface_digest": question_gate.question_surface_digest(graph),
        "proposal_digest": json_digest(proposal),
        "verification_plan_digest": json_digest(plan),
        "reviewer_policy": REVIEW_POLICY,
        "review_contract_digest": json_digest({
            "prompt_policy": REVIEW_PROMPT_POLICY,
            "methods": question_gate.METHODS,
            "challenge_classes": sorted(question_gate.CHALLENGE_CLASSES),
            "dispositions": sorted(question_gate.DISPOSITIONS),
        }),
        "reviewer_model": config.get("reviewer_model"),
        "reviewer_reasoning_effort": config.get("reviewer_reasoning_effort"),
    }
    return json_digest(identity).split(":", 1)[1], identity


def load_cached_review(cache_path: Path, identity: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any] | None:
    if not cache_path.is_file():
        return None
    value = load_json(cache_path, "decomposition review cache")
    fields = {"schema_version", "policy", "key", "identity", "review_digest", "review", "created_at"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("decomposition review cache has invalid fields")
    key = json_digest(identity).split(":", 1)[1]
    review = value.get("review")
    if (
        value.get("schema_version") != 1
        or value.get("policy") != REVIEW_CACHE_POLICY
        or value.get("key") != key
        or value.get("identity") != identity
        or value.get("review_digest") != json_digest(review)
        or not isinstance(value.get("created_at"), str)
    ):
        raise ValueError("decomposition review cache failed content-address validation")
    if isinstance(review, dict):
        apply_review_gate(graph, review)
    if question_gate.validate_review(review, graph, expected_graph_digest=str(identity["review_surface_digest"])):
        raise ValueError("decomposition review cache is stale or invalid")
    return review


def cache_review(cache_path: Path, identity: dict[str, Any], review: dict[str, Any]) -> None:
    key = json_digest(identity).split(":", 1)[1]
    atomic_json(cache_path, {
        "schema_version": 1,
        "policy": REVIEW_CACHE_POLICY,
        "key": key,
        "identity": identity,
        "review_digest": json_digest(review),
        "review": review,
        "created_at": now_utc(),
    })


def apply_review_gate(graph: dict[str, Any], review: dict[str, Any]) -> None:
    pivotal = [
        {"id": finding.get("id"), "question": finding.get("question"), "impacts": finding.get("impacts")}
        for finding in review.get("findings", [])
        if isinstance(finding, dict) and finding.get("disposition") == "pivotal_open"
    ]
    graph["question_gate"]["status"] = "open" if pivotal else "clear"
    graph["question_gate"]["unresolved_pivotal"] = pivotal


def obtain_review(
    workflow_dir: Path, candidate: Path, proposal: dict[str, Any], codex_bin: str,
    config: dict[str, Any], reviewer_id: str, review_file: Path | None,
) -> tuple[dict[str, Any], str, bool]:
    graph = load_json(candidate / "graph.json", "candidate graph")
    plan = load_json(candidate / "integrity" / "verification-plan.json", "candidate plan")
    reviewed_surface_digest = question_gate.question_surface_digest(graph)
    cache_key, identity = review_cache_key(graph, proposal, plan, config)
    cache_path = workflow_dir / "runtime" / "decompositions" / "cache" / f"{cache_key}.json"
    cached = load_cached_review(cache_path, identity, graph)
    if cached is not None:
        return cached, cache_key, True
    if review_file is not None:
        review = load_json(review_file, "decomposition review")
    else:
        if not config.get("reviewer_model"):
            raise ValueError("automatic decomposition requires a configured low-cost reviewer model")
        final_path = candidate / "runtime" / "decompositions" / ".review-final.json"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            codex_bin, "exec", "--json", "--output-last-message", str(final_path), "--cd", str(candidate),
            "--sandbox", "read-only", "--config", 'approval_policy="never"', "--ephemeral",
            "--model", str(config["reviewer_model"]),
            "--config", f"model_reasoning_effort={config['reviewer_reasoning_effort']}", "-",
        ]
        completed = subprocess.run(
            command, input=review_prompt(graph, proposal, plan, reviewer_id), capture_output=True, text=True, timeout=300, check=False,
        )
        if completed.returncode or not final_path.is_file():
            raise ValueError(f"independent decomposition review failed: {(completed.stderr or completed.stdout).strip()[-1000:]}")
        review = load_json(final_path, "decomposition review")
    if isinstance(review, dict):
        apply_review_gate(graph, review)
    errors = question_gate.validate_review(review, graph, expected_graph_digest=reviewed_surface_digest)
    if errors:
        raise ValueError("independent decomposition review rejected: " + "; ".join(errors))
    cache_review(cache_path, identity, review)
    return review, cache_key, False


def dependency_descendants(graph: dict[str, Any], node_id: str) -> set[str]:
    reverse: dict[str, set[str]] = {}
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        for dependency in node.get("depends_on", []):
            if isinstance(dependency, str):
                reverse.setdefault(dependency, set()).add(str(node.get("id")))
    found: set[str] = set()
    stack = list(reverse.get(node_id, set()))
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        stack.extend(reverse.get(current, set()))
    return found


def semantic_rebase_request(graph: dict[str, Any], node_id: str, review: dict[str, Any]) -> dict[str, Any]:
    pivotal = [
        finding for finding in review.get("findings", [])
        if isinstance(finding, dict) and finding.get("disposition") == "pivotal_open"
    ]
    if not pivotal:
        raise ValueError("open decomposition review has no pivotal finding")
    impacts = sorted({impact for finding in pivotal for impact in finding.get("impacts", [])})
    affected = [node_id, *sorted(dependency_descendants(graph, node_id))]
    questions = [str(finding["question"]).strip() for finding in pivotal]
    rationales = [str(finding["rationale"]).strip() for finding in pivotal]
    question = f"Rebase branch {node_id} before decomposition: " + " | ".join(questions)
    triage = {
        "blocking_scope": "branch",
        "impacts": impacts,
        "affected_nodes": affected,
        "no_safe_default_reason": " ".join(rationales)[:1000],
        "resolution_mode": "rebase",
        "request_graph_digest": canonical_graph_digest(graph),
        "authority_capabilities": [],
    }
    alternatives = [
        "Revise the affected branch contract to resolve every pivotal finding",
        "Provide constraints that preserve the current contract and permit a new decomposition review",
        "Reject the decomposition and keep this branch blocked",
    ]
    risks = [
        "Proceeding without a semantic decision can produce contract-correct work that misses user intent.",
        "A rebase invalidates stale branch approvals, executor digests, and verification bindings.",
    ]
    surface = json.dumps(
        {"question": question, "alternatives": alternatives, "risks": risks, "triage": triage},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    digest = "sha256:" + hashlib.sha256(surface).hexdigest()
    return {
        "request_id": f"decomposition-rebase-{node_id.lower()}-{digest.split(':', 1)[1][:12]}",
        "digest": digest,
        "question": question,
        "alternatives": alternatives,
        "risks": risks,
        "triage": triage,
    }


def validate_candidate(candidate: Path, repo_root: Path) -> dict[str, Any]:
    memory_state.command_bind(candidate, repo_root)
    evidence_runner.command_lock(candidate, repo_root)
    graph = load_json(candidate / "graph.json", "candidate graph")
    for node in graph.get("nodes", []):
        if isinstance(node, dict) and node.get("kind") != "expand":
            load_executor(candidate, str(node.get("id")))
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "validate_graph.py"), str(candidate / "graph.json"), "--phase", "executable", "--ready"],
        capture_output=True, text=True, check=False,
    )
    if completed.returncode:
        raise ValueError(f"decomposition candidate is not executable: {(completed.stdout + completed.stderr).strip()}")
    question_gate.validate(candidate)
    return graph


def copy_file(source: Path, destination: Path) -> None:
    atomic_bytes(destination, source.read_bytes())


def copy_backup_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"decomposition backup refuses symlink: {path.relative_to(source)}")
        relative = path.relative_to(source)
        if path.is_dir():
            (destination / relative).mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            copy_file(path, destination / relative)


def backup_manifest_value(backup: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path in sorted(backup.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"decomposition backup contains symlink: {path.relative_to(backup)}")
        if path.is_file():
            entries.append({
                "path": path.relative_to(backup).as_posix(),
                "digest": sha256(path),
                "size": path.stat().st_size,
            })
    return {
        "schema_version": 1,
        "policy": BACKUP_MANIFEST_POLICY,
        "leaves": entries,
        "root_digest": json_digest(entries),
        "created_at": now_utc(),
    }


def verify_backup_manifest(record_dir: Path, journal: dict[str, Any]) -> dict[str, Any]:
    relative = journal.get("backup_manifest")
    digest = journal.get("backup_manifest_digest")
    if relative != "backup-manifest.json" or not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
        raise ValueError("decomposition journal backup manifest binding is invalid")
    path = record_dir / relative
    if not path.is_file() or sha256(path) != digest:
        raise ValueError("decomposition backup manifest digest mismatch")
    value = load_json(path, "decomposition backup manifest")
    fields = {"schema_version", "policy", "leaves", "root_digest", "created_at"}
    if not isinstance(value, dict) or set(value) != fields or value.get("schema_version") != 1 or value.get("policy") != BACKUP_MANIFEST_POLICY:
        raise ValueError("decomposition backup manifest has invalid fields")
    leaves = value.get("leaves")
    if not isinstance(leaves, list) or value.get("root_digest") != json_digest(leaves) or not isinstance(value.get("created_at"), str):
        raise ValueError("decomposition backup manifest root is invalid")
    expected_paths = set(journal.get("core_present", []))
    backup = record_dir / "backup"
    if journal.get("reviews_present") is True:
        reviews = backup / "integrity" / "reviews"
        if not reviews.is_dir():
            raise ValueError("decomposition backup is missing integrity reviews")
        expected_paths.update(
            path.relative_to(backup).as_posix() for path in reviews.rglob("*") if path.is_file() and not path.is_symlink()
        )
    seen: set[str] = set()
    for leaf in leaves:
        if not isinstance(leaf, dict) or set(leaf) != {"path", "digest", "size"}:
            raise ValueError("decomposition backup manifest leaf is invalid")
        relative_path = leaf.get("path")
        if (
            not isinstance(relative_path, str) or not relative_path or relative_path in seen
            or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts
        ):
            raise ValueError("decomposition backup manifest path is invalid")
        saved = backup / relative_path
        if (
            saved.is_symlink() or not saved.is_file() or leaf.get("digest") != sha256(saved)
            or not isinstance(leaf.get("size"), int) or leaf["size"] != saved.stat().st_size
        ):
            raise ValueError(f"decomposition backup leaf failed verification: {relative_path}")
        seen.add(relative_path)
    if seen != expected_paths:
        raise ValueError("decomposition backup manifest does not exactly cover the backup contract")
    return value


def write_journal(record_dir: Path, journal: dict[str, Any], status: str, error: str | None = None) -> None:
    journal["status"] = status
    journal["updated_at"] = now_utc()
    journal["error"] = error
    atomic_json(record_dir / "journal.json", journal)


def validate_journal(record_dir: Path, value: Any) -> dict[str, Any]:
    fields = {
        "schema_version", "policy", "revision_id", "node_id", "children", "core_files", "core_present",
        "reviews_present", "backup_manifest", "backup_manifest_digest", "old_graph_digest", "new_graph_digest", "runtime_revision_before", "status",
        "created_at", "updated_at", "error",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"invalid decomposition journal fields: {record_dir.name}")
    if value.get("schema_version") != 1 or value.get("policy") != JOURNAL_POLICY or value.get("revision_id") != record_dir.name:
        raise ValueError(f"invalid decomposition journal identity: {record_dir.name}")
    node_id = value.get("node_id")
    children = value.get("children")
    if not isinstance(node_id, str) or not NODE_ID_RE.fullmatch(node_id):
        raise ValueError("decomposition journal node_id is invalid")
    if (
        not isinstance(children, list) or not children or len(children) != len(set(children))
        or any(not isinstance(child, str) or not NODE_ID_RE.fullmatch(child) or not child.startswith(f"{node_id}.") for child in children)
    ):
        raise ValueError("decomposition journal children are invalid")
    if value.get("core_files") != list(CORE_FILES):
        raise ValueError("decomposition journal core file contract is invalid")
    core_present = value.get("core_present")
    if not isinstance(core_present, list) or len(core_present) != len(set(core_present)) or not set(core_present).issubset(CORE_FILES):
        raise ValueError("decomposition journal core_present is invalid")
    if not isinstance(value.get("reviews_present"), bool):
        raise ValueError("decomposition journal reviews_present must be boolean")
    if value.get("backup_manifest") != "backup-manifest.json":
        raise ValueError("decomposition journal backup_manifest is invalid")
    manifest_digest = value.get("backup_manifest_digest")
    if manifest_digest is not None and (not isinstance(manifest_digest, str) or not DIGEST_RE.fullmatch(manifest_digest)):
        raise ValueError("decomposition journal backup_manifest_digest is invalid")
    if value.get("status") != "preparing" and manifest_digest is None:
        raise ValueError("prepared decomposition journal requires a backup manifest digest")
    if any(not isinstance(value.get(field), str) or not DIGEST_RE.fullmatch(value[field]) for field in ("old_graph_digest", "new_graph_digest")):
        raise ValueError("decomposition journal graph digests are invalid")
    revision = value.get("runtime_revision_before")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValueError("decomposition journal runtime revision is invalid")
    if value.get("status") not in {"preparing", "prepared", "committing", "committed", "finalized", "rolled_back"}:
        raise ValueError("decomposition journal status is invalid")
    if any(not isinstance(value.get(field), str) or not value[field] for field in ("created_at", "updated_at")):
        raise ValueError("decomposition journal timestamps are invalid")
    if value.get("error") is not None and not isinstance(value.get("error"), str):
        raise ValueError("decomposition journal error must be null or a string")
    return value


def archive_aborted_result(workflow_dir: Path, record_dir: Path, node_id: str) -> None:
    if not NODE_ID_RE.fullmatch(node_id):
        raise ValueError("decomposition journal result node is invalid")
    source = inside(workflow_dir, f"runtime/results/{node_id}.json", "decomposition result")
    destination = record_dir / "aborted-result.json"
    if source.is_file():
        if destination.is_file():
            if source.read_bytes() != destination.read_bytes():
                raise ValueError("aborted decomposition result conflicts with its durable archive")
            source.unlink()
        else:
            source.replace(destination)
        fsync_directory(source.parent)
        fsync_directory(destination.parent)


def restore_backup(workflow_dir: Path, record_dir: Path, journal: dict[str, Any], reason: str) -> None:
    verify_backup_manifest(record_dir, journal)
    backup = record_dir / "backup"
    present = set(journal.get("core_present", []))
    for child in journal.get("children", []):
        if isinstance(child, str):
            shutil.rmtree(inside(workflow_dir, f"nodes/{child}", "decomposition child"), ignore_errors=True)
    for relative in journal.get("core_files", []):
        if not isinstance(relative, str) or relative not in CORE_FILES:
            raise ValueError("decomposition journal core file list is invalid")
        saved = backup / relative
        target = workflow_dir / relative
        if relative in present:
            if not saved.is_file():
                raise ValueError(f"decomposition backup is missing {relative}")
            copy_file(saved, target)
        elif target.is_file():
            target.unlink()
    live_reviews = workflow_dir / "integrity" / "reviews"
    if live_reviews.exists():
        shutil.rmtree(live_reviews)
    saved_reviews = backup / "integrity" / "reviews"
    if journal.get("reviews_present") is True:
        if not saved_reviews.is_dir():
            raise ValueError("decomposition backup is missing integrity reviews")
        shutil.copytree(saved_reviews, live_reviews)
    for name in REVISION_ARTIFACTS:
        artifact = record_dir / name
        if artifact.is_file():
            artifact.unlink()
    archive_aborted_result(workflow_dir, record_dir, str(journal.get("node_id")))
    restored = load_json(workflow_dir / "graph.json", "restored graph")
    if canonical_graph_digest(restored) != journal.get("old_graph_digest"):
        raise ValueError("decomposition rollback did not restore the old graph digest")
    write_journal(record_dir, journal, "rolled_back", reason)


def finalize_committed_runtime(workflow_dir: Path, journal: dict[str, Any]) -> None:
    path = workflow_dir / "runtime.json"
    runtime = load_json(path, "runtime")
    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object")
    config = default_config() if runtime.get("decomposition") is None else validate_config(runtime["decomposition"])
    before = journal.get("runtime_revision_before")
    if not isinstance(before, int) or isinstance(before, bool) or before < 0:
        raise ValueError("decomposition journal runtime revision is invalid")
    if config["revision"] == before:
        config["revision"] += 1
    elif config["revision"] != before + 1:
        raise ValueError("runtime decomposition revision diverged from committed journal")
    proof_path = f"runtime/decompositions/{journal['revision_id']}/proof.json"
    config.update(
        status="applied", active_node=journal["node_id"], last_proof=proof_path,
        failure=None, updated_at=now_utc(),
    )
    runtime["decomposition"] = validate_config(config)
    grants = runtime.get("authority_grants") if isinstance(runtime.get("authority_grants"), dict) else {}
    grants.pop(str(journal["node_id"]), None)
    atomic_json(path, runtime)


def recover_pending(workflow_dir: Path, repo_root: Path) -> list[dict[str, str]]:
    """Recover durable decomposition journals before graph validation or result reconciliation."""
    workflow_dir = workflow_dir.resolve()
    recovered: list[dict[str, str]] = []
    root = workflow_dir / "runtime" / "decompositions"
    if not root.is_dir():
        return recovered
    for record_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        journal_path = record_dir / "journal.json"
        if not journal_path.is_file():
            continue
        journal = validate_journal(record_dir, load_json(journal_path, "decomposition journal"))
        status = journal.get("status")
        if status in {"finalized", "rolled_back"}:
            continue
        if status != "preparing":
            verify_backup_manifest(record_dir, journal)
        if status == "committed":
            graph = load_json(workflow_dir / "graph.json", "committed graph")
            proof = record_dir / "proof.json"
            if proof.is_file() and canonical_graph_digest(graph) == journal.get("new_graph_digest"):
                try:
                    validate_candidate(workflow_dir, repo_root)
                    finalize_committed_runtime(workflow_dir, journal)
                    write_journal(record_dir, journal, "finalized")
                    recovered.append({"revision_id": record_dir.name, "action": "finalized"})
                except Exception as error:
                    restore_backup(
                        workflow_dir, record_dir, journal,
                        f"Committed revision failed recovery validation and was rolled back: {error}",
                    )
                    update_runtime(
                        workflow_dir, "blocked", str(journal.get("node_id")), None,
                        "Committed decomposition failed recovery validation and was rolled back.",
                    )
                    recovered.append({"revision_id": record_dir.name, "action": "rolled_back"})
                continue
            restore_backup(workflow_dir, record_dir, journal, "Committed revision failed recovery validation; rolled back.")
            update_runtime(
                workflow_dir, "blocked", str(journal.get("node_id")), None,
                "Committed decomposition failed recovery validation and was rolled back.",
            )
            recovered.append({"revision_id": record_dir.name, "action": "rolled_back"})
            continue
        if status in {"preparing", "prepared"}:
            archive_aborted_result(workflow_dir, record_dir, str(journal.get("node_id")))
            write_journal(record_dir, journal, "rolled_back", "Recovered before live mutation began.")
            update_runtime(
                workflow_dir, "blocked", str(journal.get("node_id")), None,
                "Recovered an interrupted decomposition before live mutation; node is eligible for a corrected retry.",
            )
            recovered.append({"revision_id": record_dir.name, "action": "rolled_back"})
            continue
        if status == "committing":
            restore_backup(workflow_dir, record_dir, journal, "Recovered interrupted live commit.")
            update_runtime(
                workflow_dir, "blocked", str(journal.get("node_id")), None,
                "Recovered and rolled back an interrupted live decomposition commit.",
            )
            recovered.append({"revision_id": record_dir.name, "action": "rolled_back"})
            continue
        raise ValueError(f"decomposition journal has unknown status: {status!r}")
    return recovered


def commit_candidate(
    workflow_dir: Path, candidate: Path, repo_root: Path, node_id: str, child_ids: list[str], revision_id: str,
    proof: dict[str, Any], runtime_revision_before: int, fault_hook: Callable[[str], None] | None = None,
) -> None:
    record_dir = workflow_dir / "runtime" / "decompositions" / revision_id
    backup = record_dir / "backup"
    record_dir.mkdir(parents=True, exist_ok=False)
    journal = {
        "schema_version": 1,
        "policy": JOURNAL_POLICY,
        "revision_id": revision_id,
        "node_id": node_id,
        "children": child_ids,
        "core_files": list(CORE_FILES),
        "core_present": [relative for relative in CORE_FILES if (workflow_dir / relative).is_file()],
        "reviews_present": (workflow_dir / "integrity" / "reviews").is_dir(),
        "backup_manifest": "backup-manifest.json",
        "backup_manifest_digest": None,
        "old_graph_digest": proof["old_graph_digest"],
        "new_graph_digest": proof["new_graph_digest"],
        "runtime_revision_before": runtime_revision_before,
        "status": "preparing",
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "error": None,
    }
    atomic_json(record_dir / "journal.json", journal)
    backup.mkdir(parents=True, exist_ok=False)
    for relative in CORE_FILES:
        source = workflow_dir / relative
        if source.is_file():
            if source.is_symlink():
                raise ValueError(f"decomposition backup refuses symlink: {relative}")
            destination = backup / relative
            copy_file(source, destination)
    old_reviews = workflow_dir / "integrity" / "reviews"
    if old_reviews.is_dir():
        copy_backup_tree(old_reviews, backup / "integrity" / "reviews")
    manifest_path = record_dir / "backup-manifest.json"
    atomic_json(manifest_path, backup_manifest_value(backup))
    journal["backup_manifest_digest"] = sha256(manifest_path)
    verify_backup_manifest(record_dir, journal)
    write_journal(record_dir, journal, "prepared")
    if fault_hook is not None:
        fault_hook("prepared")
    try:
        write_journal(record_dir, journal, "committing")
        for index, child in enumerate(child_ids):
            target = workflow_dir / "nodes" / child
            shutil.copytree(candidate / "nodes" / child, target)
            if index == 0 and fault_hook is not None:
                fault_hook("child-copied")
        for relative in CORE_FILES:
            copy_file(candidate / relative, workflow_dir / relative)
        if old_reviews.is_dir():
            shutil.rmtree(old_reviews)
        shutil.copytree(candidate / "integrity" / "reviews", old_reviews)
        validate_candidate(workflow_dir, repo_root)
        if fault_hook is not None:
            fault_hook("validated")
        atomic_json(record_dir / "proof.json", proof)
        atomic_json(record_dir / "proposal.json", proof["proposal"])
        atomic_json(record_dir / "review.json", proof["review"])
        write_journal(record_dir, journal, "committed")
        if fault_hook is not None:
            fault_hook("committed")
    except Exception as error:
        restore_backup(workflow_dir, record_dir, journal, f"Commit failed and was rolled back: {error}")
        raise


def update_runtime(workflow_dir: Path, status: str, node_id: str | None, proof_path: str | None, failure: str | None) -> None:
    path = workflow_dir / "runtime.json"
    runtime = load_json(path, "runtime")
    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object")
    config = default_config() if runtime.get("decomposition") is None else validate_config(runtime["decomposition"])
    if status == "applied":
        config["revision"] += 1
    config.update(status=status, active_node=node_id, last_proof=proof_path, failure=failure, updated_at=now_utc())
    runtime["decomposition"] = validate_config(config)
    grants = runtime.get("authority_grants") if isinstance(runtime.get("authority_grants"), dict) else {}
    if node_id is not None:
        grants.pop(node_id, None)
    atomic_json(path, runtime)


def apply(
    workflow_dir: Path, repo_root: Path, node_id: str, result: dict[str, Any], codex_bin: str,
    review_file: Path | None = None, fault_hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workflow_dir = workflow_dir.resolve()
    repo_root = repo_root.resolve()
    runtime = load_json(workflow_dir / "runtime.json", "runtime")
    config = default_config() if not isinstance(runtime, dict) or runtime.get("decomposition") is None else validate_config(runtime["decomposition"])
    proposal = result.get("decomposition")
    if result.get("status") != "decompose" or not isinstance(proposal, dict):
        raise ValueError("decomposition broker requires a decompose result with proposal")
    if (
        result.get("outputs") != [] or result.get("evidence") != [] or result.get("memory_delta") is not None
        or result.get("request") is not None or result.get("verification") is not None
    ):
        raise ValueError("decompose result must not carry outputs, evidence, memory, request, or verification")
    attempt = result.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 0:
        raise ValueError("decompose result attempt must be a non-negative integer")
    revision_id = f"{node_id.lower()}-a{attempt}-{json_digest(proposal).split(':', 1)[1][:12]}"
    reviewer_id = f"decomposition-review-{revision_id}"
    update_runtime(workflow_dir, "reviewing", node_id, None, None)
    try:
        with tempfile.TemporaryDirectory(prefix="graphflow-decomposition-") as directory:
            candidate = Path(directory) / "workflow"
            shutil.copytree(workflow_dir, candidate, symlinks=True)
            old_graph = load_json(candidate / "graph.json", "old graph")
            old_digest = canonical_graph_digest(old_graph)
            graph, created = build_candidate(candidate, node_id, proposal)
            review, cache_key, cache_hit = obtain_review(
                workflow_dir, candidate, proposal, codex_bin, config, reviewer_id, review_file,
            )
            if review.get("status") == "open":
                request = semantic_rebase_request(old_graph, node_id, review)
                decision_path = workflow_dir / "runtime" / "decompositions" / "rejected" / f"{revision_id}.json"
                atomic_json(decision_path, {
                    "schema_version": 1,
                    "policy": "semantic-rebase-decision-v1",
                    "revision_id": revision_id,
                    "node_id": node_id,
                    "proposal_digest": json_digest(proposal),
                    "review_digest": json_digest(review),
                    "review_cache": f"runtime/decompositions/cache/{cache_key}.json",
                    "request_id": request["request_id"],
                    "request_digest": request["digest"],
                    "created_at": now_utc(),
                })
                update_runtime(
                    workflow_dir, "waiting_rebase", node_id, None,
                    "Independent review found a pivotal semantic issue; the affected branch requires digest-bound rebase confirmation.",
                )
                return {
                    "status": "waiting_rebase",
                    "revision_id": revision_id,
                    "request": request,
                    "review_cache_key": cache_key,
                    "review_cache_hit": cache_hit,
                    "decision_artifact": str(decision_path.relative_to(workflow_dir)),
                }
            atomic_json(candidate / "question-review.json", review)
            question_gate.lock(candidate)
            validated = validate_candidate(candidate, repo_root)
            child_ids = sorted(created)
            proof = {
                "schema_version": 1,
                "policy": POLICY,
                "revision_id": revision_id,
                "parent_node": node_id,
                "children": child_ids,
                "terminal_child": child_id(node_id, str(proposal["terminal_child"])),
                "old_graph_digest": old_digest,
                "new_graph_digest": canonical_graph_digest(validated),
                "proposal_digest": json_digest(proposal),
                "review_digest": json_digest(review),
                "review_cache_key": cache_key,
                "review_cache_hit": cache_hit,
                "contract_equivalent": True,
                "budget_nonincreasing": True,
                "measure_strictly_decreasing": True,
                "applied_at": now_utc(),
                "proposal": proposal,
                "review": review,
            }
            commit_candidate(
                workflow_dir, candidate, repo_root, node_id, child_ids, revision_id, proof, config["revision"], fault_hook,
            )
        proof_path = f"runtime/decompositions/{revision_id}/proof.json"
        journal = load_json(workflow_dir / "runtime" / "decompositions" / revision_id / "journal.json", "decomposition journal")
        if not isinstance(journal, dict):
            raise ValueError("committed decomposition journal is invalid")
        finalize_committed_runtime(workflow_dir, journal)
        write_journal(workflow_dir / "runtime" / "decompositions" / revision_id, journal, "finalized")
        return {"status": "applied", "revision_id": revision_id, "children": child_ids, "proof": proof_path}
    except Exception as error:
        update_runtime(workflow_dir, "blocked", node_id, None, str(error))
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workflow_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--node", required=True)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--codex-bin", default=shutil.which("codex") or "codex")
    parser.add_argument("--review-file", type=Path)
    args = parser.parse_args()
    try:
        recover_pending(args.workflow_dir.resolve(), args.repo_root.resolve())
        result_path = args.result.resolve() if args.result else args.workflow_dir.resolve() / "runtime" / "results" / f"{args.node}.json"
        result = load_json(result_path, "decomposition result")
        if not isinstance(result, dict):
            raise ValueError("decomposition result must be an object")
        outcome = apply(
            args.workflow_dir.resolve(), args.repo_root.resolve(), args.node, result, args.codex_bin,
            args.review_file.resolve() if args.review_file else None,
        )
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(outcome, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
