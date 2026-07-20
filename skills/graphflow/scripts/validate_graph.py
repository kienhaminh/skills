#!/usr/bin/env python3
"""Validate a workflow graph without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from collections import defaultdict, deque
from pathlib import PurePosixPath
from typing import Any


KINDS = {"expand", "execute", "integrate", "verify"}
WAITING_STATUSES = {"waiting_user", "waiting_approval", "waiting_external"}
NODE_STATUSES = {"pending", "active", "stale", "blocked", "complete", "failed", *WAITING_STATUSES}
EXPAND_STATUSES = {"pending", "active", "stale", "blocked", "expanded", "failed", *WAITING_STATUSES}
DEPENDENCY_GATED_STATUSES = {"active", "stale", "complete", *WAITING_STATUSES}
ISOLATION_MODES = {"coordinator", "shared-readonly", "worktree", "integration"}
OPERATION_SKILLS = {
    "analysis": None,
    "bootstrap": "bootstrap",
    "decomposition": None,
    "diagnosis": "debugging",
    "docs-sync": "sync-docs",
    "feature-plan": "grill-me",
    "implementation": "implement",
    "integration": None,
    "problem-framing": "brainstorming",
    "prototyping": None,
    "story-slicing": "to-stories",
    "test-design": "to-tdd",
    "verification": None,
    "worktree-management": "worktree",
}
PROJECT_TRANSFORMATION_SKILLS = {skill for skill in OPERATION_SKILLS.values() if skill is not None}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
WORKFLOW_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GLOB_RE = re.compile(r"[*?]")
METHOD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .+&'/-]{0,63}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
INTEGRITY_LEVELS = {"low", "medium", "high"}
EXECUTOR_TYPES = {"command", "agent"}
QUESTION_METHODS = ["Rumsfeld Matrix", "Value of Information", "Reversibility"]
QUESTION_IMPACTS = {
    "objective", "acceptance", "scope", "authority", "intent_baseline",
    "verification_oracle", "cost_risk", "irreversible_action",
}
INTEGRITY_CONFIG_FIELDS = {
    "schema_version", "level", "status", "verification_plan", "lock",
    "plan_digest", "runner", "runner_digest", "evidence_dir", "completion_rule",
}
CANONICAL_METHODS = {
    "Attack Trees",
    "Bayesian Updating",
    "Boundary Value Analysis",
    "Calibration",
    "Characterization Testing",
    "Consumer-Driven Contracts",
    "Contract Testing",
    "Defense in Depth",
    "Differential Testing",
    "Docs as Code",
    "Double Diamond",
    "DRY",
    "Dry Run",
    "Equivalence Partitioning",
    "Evidence Hierarchy",
    "FMEA",
    "Fault Tree Analysis",
    "Five Whys",
    "INVEST",
    "KISS",
    "MECE",
    "Metamorphic Testing",
    "MoSCoW",
    "Negative Testing",
    "Poka-Yoke",
    "Popperian Falsification",
    "Premortem",
    "Rumsfeld Matrix",
    "Scientific Method",
    "Single Source of Truth",
    "STRIDE",
    "TDD",
    "Throwaway Prototyping",
    "Trunk-Based Development",
    "Value of Information",
    "Vertical Slicing",
    "Walking Skeleton",
    "Wizard of Oz",
    "YAGNI",
    "Evolutionary Prototyping",
    "Reversibility",
}
PRIMARY_METHODS = {
    "analysis": {"Rumsfeld Matrix", "Scientific Method", "FMEA", "STRIDE", "Bayesian Updating"},
    "bootstrap": {"Walking Skeleton"},
    "decomposition": {"MECE"},
    "diagnosis": {"Scientific Method"},
    "docs-sync": {"Single Source of Truth"},
    "feature-plan": {"Double Diamond"},
    "implementation": {"YAGNI", "TDD", "Contract Testing", "Walking Skeleton"},
    "integration": {"Contract Testing"},
    "problem-framing": {"Rumsfeld Matrix"},
    "prototyping": {"Throwaway Prototyping", "Evolutionary Prototyping", "Characterization Testing", "Dry Run"},
    "story-slicing": {"INVEST"},
    "test-design": {"TDD"},
    "verification": {"Popperian Falsification"},
    "worktree-management": {"Trunk-Based Development"},
}
CLAIM_STATES = {"verified", "observed", "inferred", "unverified"}
CONFIDENCE_BY_STATE = {
    "verified": {"high", "medium"},
    "observed": {"medium", "low"},
    "inferred": {"low"},
    "unverified": {"none"},
}


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: Any) -> bool:
    return isinstance(value, list) and all(nonempty_string(item) for item in value)


def add(errors: list[str], where: str, message: str) -> None:
    errors.append(f"{where}: {message}")


def normalize_write_path(path: str) -> str | None:
    if GLOB_RE.search(path) or path.startswith("/") or "\\" in path:
        return None
    normalized = posixpath.normpath(path)
    if normalized in {".", ".."} or normalized.startswith("../"):
        return None
    return str(PurePosixPath(normalized))


def normalize_artifact_path(path: str) -> str | None:
    if GLOB_RE.search(path) or "\\" in path:
        return None
    normalized = posixpath.normpath(path)
    if normalized in {".", "..", "/"} or normalized.startswith("../"):
        return None
    return str(PurePosixPath(normalized))


def paths_overlap(left: str, right: str) -> bool:
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    shared = min(len(left_parts), len(right_parts))
    return left_parts[:shared] == right_parts[:shared]


def has_cycle(node_ids: set[str], adjacency: dict[str, list[str]]) -> bool:
    indegree = {node_id: 0 for node_id in node_ids}
    for source in node_ids:
        for target in adjacency.get(source, []):
            if target in indegree:
                indegree[target] += 1
    queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for target in adjacency.get(current, []):
            if target not in indegree:
                continue
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return visited != len(node_ids)


def dependency_ancestors(node_id: str, dependencies: dict[str, list[str]]) -> set[str]:
    ancestors: set[str] = set()
    stack = list(dependencies.get(node_id, []))
    while stack:
        current = stack.pop()
        if current in ancestors:
            continue
        ancestors.add(current)
        stack.extend(dependencies.get(current, []))
    return ancestors


def validate(data: Any, phase: str) -> tuple[list[str], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    ready: list[str] = []
    if not isinstance(data, dict):
        return ["graph: root must be an object"], warnings, ready

    version = data.get("version")
    if version != 3:
        add(errors, "version", "must equal 3; migrate legacy workflows before use")
    workflow_id = data.get("workflow_id")
    if not nonempty_string(workflow_id) or not WORKFLOW_ID_RE.fullmatch(workflow_id):
        add(errors, "workflow_id", "must be kebab-case")

    goal_field = "objective"
    goal = data.get(goal_field)
    requirements: dict[str, dict[str, Any]] = {}
    if not isinstance(goal, dict):
        add(errors, goal_field, "must be an object")
    else:
        if not nonempty_string(goal.get("statement")):
            add(errors, f"{goal_field}.statement", "must be a non-empty string")
        raw_requirements = goal.get("requirements")
        if not isinstance(raw_requirements, list) or not raw_requirements:
            add(errors, f"{goal_field}.requirements", "must be a non-empty list")
        else:
            for index, requirement in enumerate(raw_requirements):
                where = f"{goal_field}.requirements[{index}]"
                if not isinstance(requirement, dict):
                    add(errors, where, "must be an object")
                    continue
                requirement_id = requirement.get("id")
                if not nonempty_string(requirement_id) or not ID_RE.fullmatch(requirement_id):
                    add(errors, f"{where}.id", "must be a stable identifier")
                elif requirement_id in requirements:
                    add(errors, f"{where}.id", f"duplicate requirement {requirement_id}")
                else:
                    requirements[requirement_id] = requirement
                if not nonempty_string(requirement.get("text")):
                    add(errors, f"{where}.text", "must be a non-empty string")
                if not string_list(requirement.get("acceptance")) or not requirement["acceptance"]:
                    add(errors, f"{where}.acceptance", "must be a non-empty string list")
        if not string_list(goal.get("out_of_scope")):
            add(errors, f"{goal_field}.out_of_scope", "must be a string list")

    constraints = data.get("constraints")
    token_budget = None
    max_parallel = None
    if not isinstance(constraints, dict):
        add(errors, "constraints", "must be an object")
    else:
        token_budget = constraints.get("token_budget")
        max_parallel = constraints.get("max_parallel")
        if not isinstance(token_budget, int) or isinstance(token_budget, bool) or token_budget <= 0:
            add(errors, "constraints.token_budget", "must be a positive integer")
            token_budget = None
        if not isinstance(max_parallel, int) or isinstance(max_parallel, bool) or max_parallel <= 0:
            add(errors, "constraints.max_parallel", "must be a positive integer")
            max_parallel = None

    execution_trust = data.get("execution_trust")
    trust_fields = {"schema_version", "policy", "workspace_registry", "progress_dir", "required_phases"}
    expected_phases = {
        "low": ["scope_accepted", "evidence_passed"],
        "medium": ["scope_accepted", "evidence_passed", "independently_verified"],
        "high": ["scope_accepted", "evidence_passed", "independently_verified", "externally_verified"],
    }
    if not isinstance(execution_trust, dict) or set(execution_trust) != trust_fields:
        add(errors, "execution_trust", f"must contain exactly {sorted(trust_fields)!r}")
    else:
        if execution_trust.get("schema_version") != 1 or execution_trust.get("policy") != "risk-adaptive-workspace-v1":
            add(errors, "execution_trust", "has an unsupported schema or policy")
        if execution_trust.get("workspace_registry") != "runtime/workspaces.json":
            add(errors, "execution_trust.workspace_registry", "must equal runtime/workspaces.json")
        if execution_trust.get("progress_dir") != "runtime/progress":
            add(errors, "execution_trust.progress_dir", "must equal runtime/progress")
        if execution_trust.get("required_phases") != expected_phases:
            add(errors, "execution_trust.required_phases", "must equal the non-compensatory risk policy")

    for field in ("goal_binding", "execution_policy", "cost_plan"):
        if field in data:
            add(errors, field, "must be supplied by the activating caller, not embedded in graph.json")

    lifecycle = data.get("lifecycle")
    if not isinstance(lifecycle, dict):
        add(errors, "lifecycle", "must be an object")
    elif lifecycle.get("status") not in {"draft", "ready", "active", "waiting", "complete", "blocked"}:
        add(errors, "lifecycle.status", "must be draft, ready, active, waiting, complete, or blocked")

    question_gate = data.get("question_gate")
    question_status = None
    unresolved_pivotal: list[Any] = []
    if not isinstance(question_gate, dict):
        add(errors, "question_gate", "must be an object")
    else:
        expected_fields = {"methods", "status", "unresolved_pivotal", "review"}
        if set(question_gate) != expected_fields:
            add(errors, "question_gate", f"must contain exactly {sorted(expected_fields)!r}")
        if question_gate.get("methods") != QUESTION_METHODS:
            add(errors, "question_gate.methods", f"must equal {QUESTION_METHODS!r}")
        question_status = question_gate.get("status")
        if question_status not in {"open", "clear"}:
            add(errors, "question_gate.status", "must be open or clear")
        raw_questions = question_gate.get("unresolved_pivotal")
        if not isinstance(raw_questions, list):
            add(errors, "question_gate.unresolved_pivotal", "must be a list")
        else:
            unresolved_pivotal = raw_questions
            seen_question_ids: set[str] = set()
            for index, question in enumerate(raw_questions):
                where = f"question_gate.unresolved_pivotal[{index}]"
                if not isinstance(question, dict) or set(question) != {"id", "question", "impacts"}:
                    add(errors, where, "must contain exactly id, question, and impacts")
                    continue
                question_id = question.get("id")
                if not nonempty_string(question_id) or not ID_RE.fullmatch(question_id):
                    add(errors, f"{where}.id", "must be a stable identifier")
                elif question_id in seen_question_ids:
                    add(errors, f"{where}.id", f"duplicate question {question_id}")
                else:
                    seen_question_ids.add(question_id)
                if not nonempty_string(question.get("question")):
                    add(errors, f"{where}.question", "must be a non-empty string")
                impacts = question.get("impacts")
                if not isinstance(impacts, list) or not impacts or any(value not in QUESTION_IMPACTS for value in impacts):
                    add(errors, f"{where}.impacts", f"must contain one or more of {sorted(QUESTION_IMPACTS)!r}")
                elif len(impacts) != len(set(impacts)):
                    add(errors, f"{where}.impacts", "contains duplicates")
        if question_status == "clear" and unresolved_pivotal:
            add(errors, "question_gate", "clear status requires no unresolved pivotal questions")
        if question_status == "open" and not unresolved_pivotal:
            add(errors, "question_gate", "open status requires at least one unresolved pivotal question")
        if phase in {"executable", "complete"} and question_status != "clear":
            add(errors, "question_gate.status", "must be clear before executable work")
        review = question_gate.get("review")
        review_fields = {"status", "artifact", "digest", "graph_digest", "reviewer_id"}
        if not isinstance(review, dict) or set(review) != review_fields:
            add(errors, "question_gate.review", f"must contain exactly {sorted(review_fields)!r}")
        else:
            review_status = review.get("status")
            if review_status not in {"required", "locked"}:
                add(errors, "question_gate.review.status", "must be required or locked")
            artifact = review.get("artifact")
            if not nonempty_string(artifact) or normalize_artifact_path(artifact) != artifact:
                add(errors, "question_gate.review.artifact", "must be a normalized explicit artifact path")
            if review_status == "required":
                if any(review.get(field) is not None for field in ("digest", "graph_digest", "reviewer_id")):
                    add(errors, "question_gate.review", "required review must leave digest, graph_digest, and reviewer_id null")
            else:
                for field in ("digest", "graph_digest"):
                    if not isinstance(review.get(field), str) or not DIGEST_RE.fullmatch(review[field]):
                        add(errors, f"question_gate.review.{field}", "must be sha256:<64 lowercase hex> when locked")
                if not nonempty_string(review.get("reviewer_id")):
                    add(errors, "question_gate.review.reviewer_id", "must be non-empty when locked")
            if phase in {"executable", "complete"} and review_status != "locked":
                add(errors, "question_gate.review.status", "must be locked before executable work")

    intent = data.get("intent_baseline")
    intent_required = None
    intent_status = None
    if not isinstance(intent, dict):
        add(errors, "intent_baseline", "must be an object")
    else:
        intent_required = intent.get("required")
        intent_status = intent.get("status")
        if not isinstance(intent_required, bool):
            add(errors, "intent_baseline.required", "must be a boolean")
        if intent_status not in {"not_required", "proposed", "approved", "rejected", "superseded"}:
            add(errors, "intent_baseline.status", "has an unknown status")
        manifest = intent.get("manifest")
        digest = intent.get("digest")
        approval = intent.get("approval")
        reason = intent.get("not_required_reason")
        if intent_required is True:
            if not nonempty_string(manifest) or normalize_artifact_path(manifest) != manifest:
                add(errors, "intent_baseline.manifest", "must be a normalized explicit artifact path")
            if intent_status == "approved":
                if not nonempty_string(digest) or not DIGEST_RE.fullmatch(digest):
                    add(errors, "intent_baseline.digest", "must be sha256:<64 lowercase hex> when approved")
                if approval not in {"user", "deterministic"}:
                    add(errors, "intent_baseline.approval", "must be user or deterministic when approved")
            elif digest is not None or approval is not None:
                add(errors, "intent_baseline", "digest and approval must be null until approved")
            if reason is not None:
                add(errors, "intent_baseline.not_required_reason", "must be null when a baseline is required")
        elif intent_required is False:
            if intent_status != "not_required":
                add(errors, "intent_baseline.status", "must be not_required when required is false")
            if any(value is not None for value in (manifest, digest, approval)):
                add(errors, "intent_baseline", "manifest, digest, and approval must be null when not required")
            if not nonempty_string(reason):
                add(errors, "intent_baseline.not_required_reason", "must explain the deterministic exemption")

    verification = data.get("verification")
    verification_outcome = None
    claims: list[dict[str, Any]] = []
    primary_claims: dict[str, list[dict[str, Any]]] = defaultdict(list)
    claim_evidence_paths: list[tuple[str, str]] = []
    if not isinstance(verification, dict):
        add(errors, "verification", "must be an object")
    else:
        verification_outcome = verification.get("outcome")
        if verification_outcome not in {"pending", "verified", "complete_with_limits", "blocked"}:
            add(errors, "verification.outcome", "has an unknown outcome")
        raw_claims = verification.get("claims")
        if not isinstance(raw_claims, list):
            add(errors, "verification.claims", "must be a list")
        else:
            seen_claim_ids: set[str] = set()
            for index, claim in enumerate(raw_claims):
                where = f"verification.claims[{index}]"
                if not isinstance(claim, dict):
                    add(errors, where, "must be an object")
                    continue
                claims.append(claim)
                claim_id = claim.get("id")
                if not nonempty_string(claim_id) or not ID_RE.fullmatch(claim_id):
                    add(errors, f"{where}.id", "must be a stable identifier")
                elif claim_id in seen_claim_ids:
                    add(errors, f"{where}.id", f"duplicate claim {claim_id}")
                else:
                    seen_claim_ids.add(claim_id)
                requirement_id = claim.get("requirement_id")
                if requirement_id is not None:
                    if not nonempty_string(requirement_id) or requirement_id not in requirements:
                        add(errors, f"{where}.requirement_id", "must reference a requirement or be null")
                    else:
                        primary_claims[requirement_id].append(claim)
                if not nonempty_string(claim.get("statement")):
                    add(errors, f"{where}.statement", "must be a non-empty string")
                state = claim.get("state")
                confidence = claim.get("confidence")
                if state not in CLAIM_STATES:
                    add(errors, f"{where}.state", "has an unknown claim state")
                elif confidence not in CONFIDENCE_BY_STATE[state]:
                    add(errors, f"{where}.confidence", f"must be one of {sorted(CONFIDENCE_BY_STATE[state])} for {state}")
                if not string_list(claim.get("limitations")):
                    add(errors, f"{where}.limitations", "must be a string list")
                raw_evidence = claim.get("evidence")
                if not isinstance(raw_evidence, list):
                    add(errors, f"{where}.evidence", "must be a list")
                    raw_evidence = []
                for evidence_index, evidence in enumerate(raw_evidence):
                    evidence_where = f"{where}.evidence[{evidence_index}]"
                    if not isinstance(evidence, dict):
                        add(errors, evidence_where, "must be an object")
                        continue
                    if not nonempty_string(evidence.get("check")):
                        add(errors, f"{evidence_where}.check", "must be a non-empty string")
                    artifact = evidence.get("artifact")
                    if not nonempty_string(artifact) or normalize_artifact_path(artifact) != artifact:
                        add(errors, f"{evidence_where}.artifact", "must be a normalized explicit artifact path")
                    else:
                        claim_evidence_paths.append((where, artifact))
                if state in {"verified", "observed"} and not raw_evidence:
                    add(errors, f"{where}.evidence", f"must contain direct evidence for {state}")

    shared_memory = data.get("shared_memory")
    if not isinstance(shared_memory, dict):
        add(errors, "shared_memory", "must be an object")
    else:
        expected_memory = {
            "schema_version": 1,
            "policy": "blackboard-event-sourcing-v1",
            "state": "memory/state.json",
            "events": "memory/events.jsonl",
            "capsules": "memory/capsules",
        }
        unknown_fields = sorted(set(shared_memory) - set(expected_memory))
        if unknown_fields:
            add(errors, "shared_memory", f"unknown fields {unknown_fields!r}")
        for field, expected in expected_memory.items():
            if shared_memory.get(field) != expected:
                add(errors, f"shared_memory.{field}", f"must equal {expected!r}")

    integrity = data.get("integrity")
    integrity_status = None
    if not isinstance(integrity, dict):
        add(errors, "integrity", "must be an object")
        integrity = {}
    else:
        unknown_fields = sorted(set(integrity) - INTEGRITY_CONFIG_FIELDS)
        missing_fields = sorted(INTEGRITY_CONFIG_FIELDS - set(integrity))
        if unknown_fields:
            add(errors, "integrity", f"unknown fields {unknown_fields!r}")
        if missing_fields:
            add(errors, "integrity", f"missing fields {missing_fields!r}")
        if integrity.get("schema_version") != 1:
            add(errors, "integrity.schema_version", "must equal 1")
        if integrity.get("level") not in INTEGRITY_LEVELS:
            add(errors, "integrity.level", f"must be one of {sorted(INTEGRITY_LEVELS)}")
        integrity_status = integrity.get("status")
        if integrity_status not in {"proposed", "locked"}:
            add(errors, "integrity.status", "must be proposed or locked")
        expected_integrity = {
            "verification_plan": "integrity/verification-plan.json",
            "lock": "integrity/lock.json",
            "runner": "workflow-evidence-runner-v1",
            "evidence_dir": "evidence/attestations",
            "completion_rule": "all-critical",
        }
        for field, expected in expected_integrity.items():
            if integrity.get(field) != expected:
                add(errors, f"integrity.{field}", f"must equal {expected!r}")
        for field in ("plan_digest", "runner_digest"):
            value = integrity.get(field)
            if integrity_status == "locked":
                if not isinstance(value, str) or not DIGEST_RE.fullmatch(value):
                    add(errors, f"integrity.{field}", "must be sha256:<64 lowercase hex> when locked")
            elif value is not None:
                add(errors, f"integrity.{field}", "must be null until locked")
        if phase in {"executable", "complete"} and integrity_status != "locked":
            add(errors, "integrity.status", "must be locked before executable work")

    optional_work = data.get("optional_work")
    optional_ids: set[str] = set()
    if not isinstance(optional_work, list):
        add(errors, "optional_work", "must be a list")
    else:
        for index, item in enumerate(optional_work):
            where = f"optional_work[{index}]"
            if not isinstance(item, dict):
                add(errors, where, "must be an object")
                continue
            item_id = item.get("id")
            if not nonempty_string(item_id) or not ID_RE.fullmatch(item_id):
                add(errors, f"{where}.id", "must be a stable identifier")
            elif item_id in optional_ids or item_id in requirements:
                add(errors, f"{where}.id", "must be unique and distinct from requirement IDs")
            else:
                optional_ids.add(item_id)
            for field in ("outcome", "source", "value"):
                if not nonempty_string(item.get(field)):
                    add(errors, f"{where}.{field}", "must be a non-empty string")
            if not string_list(item.get("risks")):
                add(errors, f"{where}.risks", "must be a string list")
            if item.get("status") not in {"deferred", "active", "complete", "dropped"}:
                add(errors, f"{where}.status", "must be deferred, active, complete, or dropped")
            estimated = item.get("estimated_cost")
            if not isinstance(estimated, dict):
                add(errors, f"{where}.estimated_cost", "must be an object")
            else:
                for field in ("tokens", "wall_time_minutes", "disk_mb"):
                    value = estimated.get(field)
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        add(errors, f"{where}.estimated_cost.{field}", "must be a non-negative integer")
                money = estimated.get("money")
                if money is not None and (not isinstance(money, (int, float)) or isinstance(money, bool) or money < 0):
                    add(errors, f"{where}.estimated_cost.money", "must be null or a non-negative number")
                currency = estimated.get("currency")
                if currency is not None and not nonempty_string(currency):
                    add(errors, f"{where}.estimated_cost.currency", "must be null or a non-empty string")

    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        add(errors, "nodes", "must be a non-empty list")
        return errors, warnings, ready

    nodes: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(raw_nodes):
        where = f"nodes[{index}]"
        if not isinstance(node, dict):
            add(errors, where, "must be an object")
            continue
        node_id = node.get("id")
        if not nonempty_string(node_id) or not ID_RE.fullmatch(node_id):
            add(errors, f"{where}.id", "must be a stable identifier")
            continue
        if node_id in nodes:
            add(errors, f"{where}.id", f"duplicate node {node_id}")
            continue
        nodes[node_id] = node

    node_ids = set(nodes)
    dependencies: dict[str, list[str]] = {}
    dependency_edges: dict[str, list[str]] = defaultdict(list)
    parent_edges: dict[str, list[str]] = defaultdict(list)
    children: dict[str, list[str]] = defaultdict(list)
    coverage: dict[str, list[str]] = defaultdict(list)
    outputs: dict[str, str] = {}
    consumes_by_node: dict[str, list[str]] = {}
    path_owners: list[tuple[str, str, str]] = []
    owned_paths_by_node: dict[str, list[str]] = defaultdict(list)
    output_artifacts: list[tuple[str, str]] = []
    decision_owners: dict[str, str] = {}
    executor_specs: dict[str, str] = {}
    executor_results: dict[str, str] = {}
    planned_tokens = 0

    for node_id, node in nodes.items():
        where = f"node {node_id}"
        kind = node.get("kind")
        status = node.get("status")
        if kind not in KINDS:
            add(errors, f"{where}.kind", f"must be one of {sorted(KINDS)}")
        allowed_statuses = EXPAND_STATUSES if kind == "expand" else NODE_STATUSES
        if status not in allowed_statuses:
            add(errors, f"{where}.status", f"must be one of {sorted(allowed_statuses)}")
        if not nonempty_string(node.get("title")):
            add(errors, f"{where}.title", "must be a non-empty string")

        parent = node.get("parent")
        if parent is not None:
            if not nonempty_string(parent) or parent not in node_ids:
                add(errors, f"{where}.parent", "must reference an existing node or be null")
            elif parent == node_id:
                add(errors, f"{where}.parent", "cannot reference itself")
            else:
                parent_edges[parent].append(node_id)
                children[parent].append(node_id)

        raw_dependencies = node.get("depends_on")
        if not string_list(raw_dependencies):
            add(errors, f"{where}.depends_on", "must be a string list")
            raw_dependencies = []
        if len(raw_dependencies) != len(set(raw_dependencies)):
            add(errors, f"{where}.depends_on", "contains duplicate dependencies")
        dependencies[node_id] = list(raw_dependencies)
        for dependency in raw_dependencies:
            if dependency not in node_ids:
                add(errors, f"{where}.depends_on", f"unknown node {dependency}")
            elif dependency == node_id:
                add(errors, f"{where}.depends_on", "cannot depend on itself")
            else:
                dependency_edges[dependency].append(node_id)

        for field in ("skills", "covers", "consumes"):
            if not string_list(node.get(field)):
                add(errors, f"{where}.{field}", "must be a string list")
                node[field] = []
            elif len(node[field]) != len(set(node[field])):
                add(errors, f"{where}.{field}", "contains duplicates")

        node_skills = node.get("skills", [])
        coordinator_skills = sorted({"graphflow", "workflow"} & set(node_skills))
        if coordinator_skills:
            add(errors, f"{where}.skills", f"must not include coordinator skills {coordinator_skills!r}")

        operations = node.get("operations")
        if not string_list(operations):
            add(errors, f"{where}.operations", "must be a non-empty string list")
            operations = []
        elif len(operations) != len(set(operations)):
            add(errors, f"{where}.operations", "contains duplicates")

        unknown_operations = [operation for operation in operations if operation not in OPERATION_SKILLS]
        if unknown_operations:
            add(errors, f"{where}.operations", f"unknown operations {unknown_operations!r}")

        required_skills: list[str] = []
        for operation in operations:
            skill = OPERATION_SKILLS.get(operation)
            if skill is not None and skill not in required_skills:
                required_skills.append(skill)
        routed_skills = [skill for skill in node_skills if skill in PROJECT_TRANSFORMATION_SKILLS]
        if routed_skills != required_skills:
            add(
                errors,
                f"{where}.skills",
                f"project-local skills must equal {required_skills!r} derived from operations {operations!r}",
            )

        if kind == "expand" and operations != ["decomposition"]:
            add(errors, f"{where}.operations", "expansion nodes must declare exactly ['decomposition']")
        if kind == "integrate" and "integration" not in operations:
            add(errors, f"{where}.operations", "integration nodes must include 'integration'")
        if kind == "verify" and operations != ["verification"]:
            add(errors, f"{where}.operations", "verification nodes must declare exactly ['verification']")

        methods = node.get("methods")
        if not string_list(methods) or not methods:
            add(errors, f"{where}.methods", "must contain one to three canonical method names")
            methods = []
        elif len(methods) != len(set(methods)):
            add(errors, f"{where}.methods", "contains duplicates")
        if len(methods) > 3:
            add(errors, f"{where}.methods", "must contain at most three method names")
        for method in methods:
            if not METHOD_RE.fullmatch(method):
                add(errors, f"{where}.methods", f"invalid canonical method name {method!r}")
            elif method not in CANONICAL_METHODS:
                add(errors, f"{where}.methods", f"unknown canonical method {method!r}")
        if operations and methods and methods[0] not in PRIMARY_METHODS.get(operations[0], set()):
            add(
                errors,
                f"{where}.methods[0]",
                f"must be a primary method for operation {operations[0]!r}: {sorted(PRIMARY_METHODS.get(operations[0], set()))}",
            )

        executor = node.get("executor")
        if kind == "expand":
            if executor is not None:
                add(errors, f"{where}.executor", "must be null for an expansion node")
        elif not isinstance(executor, dict):
            add(errors, f"{where}.executor", "must be an object for a runnable node")
        else:
            expected_fields = {"schema_version", "type", "spec", "digest", "result"}
            if set(executor) != expected_fields:
                add(errors, f"{where}.executor", f"must contain exactly {sorted(expected_fields)!r}")
            if executor.get("schema_version") != 1:
                add(errors, f"{where}.executor.schema_version", "must equal 1")
            if executor.get("type") not in EXECUTOR_TYPES:
                add(errors, f"{where}.executor.type", f"must be one of {sorted(EXECUTOR_TYPES)}")
            for field, registry in (("spec", executor_specs), ("result", executor_results)):
                value = executor.get(field)
                normalized = normalize_artifact_path(value) if isinstance(value, str) else None
                if normalized is None or normalized != value:
                    add(errors, f"{where}.executor.{field}", "must be a normalized workflow-relative path")
                elif value in registry:
                    add(errors, f"{where}.executor.{field}", f"is already assigned to node {registry[value]}")
                else:
                    registry[value] = node_id
            expected_result = f"runtime/results/{node_id}.json"
            if executor.get("result") != expected_result:
                add(errors, f"{where}.executor.result", f"must equal {expected_result!r}")
            digest = executor.get("digest")
            if phase in {"executable", "complete"}:
                if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
                    add(errors, f"{where}.executor.digest", "must lock the executor spec before execution")
            elif digest is not None and (not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest)):
                add(errors, f"{where}.executor.digest", "must be null or sha256:<64 lowercase hex>")

        for requirement_id in node.get("covers", []):
            if requirement_id not in requirements:
                add(errors, f"{where}.covers", f"unknown requirement {requirement_id}")
            else:
                coverage[requirement_id].append(node_id)

        scope = node.get("scope")
        if not isinstance(scope, dict):
            add(errors, f"{where}.scope", "must be an object")
            scope = {}
        for field in ("read", "write", "artifacts", "decisions", "forbidden"):
            if not string_list(scope.get(field)):
                add(errors, f"{where}.scope.{field}", "must be a string list")
                scope[field] = []
            elif len(scope[field]) != len(set(scope[field])):
                add(errors, f"{where}.scope.{field}", "contains duplicates")

        local_writes: list[str] = []
        for path in scope.get("write", []):
            normalized = normalize_write_path(path)
            if normalized is None:
                add(errors, f"{where}.scope.write", f"invalid explicit repository-relative path {path!r}")
                continue
            if normalized != path:
                add(errors, f"{where}.scope.write", f"path must be normalized as {normalized!r}")
            for other in local_writes:
                if paths_overlap(normalized, other):
                    add(errors, f"{where}.scope.write", f"redundant overlapping paths {other!r} and {normalized!r}")
            local_writes.append(normalized)
            path_owners.append((node_id, normalized, "write"))
            owned_paths_by_node[node_id].append(normalized)

        local_artifacts: list[str] = []
        for path in scope.get("artifacts", []):
            normalized = normalize_artifact_path(path)
            if normalized is None:
                add(errors, f"{where}.scope.artifacts", f"invalid explicit artifact path {path!r}")
                continue
            if normalized != path:
                add(errors, f"{where}.scope.artifacts", f"path must be normalized as {normalized!r}")
            for other in local_writes + local_artifacts:
                if paths_overlap(normalized, other):
                    add(errors, f"{where}.scope.artifacts", f"redundant overlapping owned paths {other!r} and {normalized!r}")
            local_artifacts.append(normalized)
            path_owners.append((node_id, normalized, "artifact"))
            owned_paths_by_node[node_id].append(normalized)

        for decision in scope.get("decisions", []):
            owner = decision_owners.get(decision)
            if owner is not None:
                add(errors, f"{where}.scope.decisions", f"{decision!r} is already owned by node {owner}")
            else:
                decision_owners[decision] = node_id

        raw_outputs = node.get("outputs")
        if not isinstance(raw_outputs, list):
            add(errors, f"{where}.outputs", "must be a list")
            raw_outputs = []
        for output_index, output in enumerate(raw_outputs):
            output_where = f"{where}.outputs[{output_index}]"
            if not isinstance(output, dict):
                add(errors, output_where, "must be an object")
                continue
            output_id = output.get("id")
            if not nonempty_string(output_id) or not ID_RE.fullmatch(output_id):
                add(errors, f"{output_where}.id", "must be a stable identifier")
            elif output_id in outputs:
                add(errors, f"{output_where}.id", f"duplicate output also produced by node {outputs[output_id]}")
            else:
                outputs[output_id] = node_id
            if not nonempty_string(output.get("description")):
                add(errors, f"{output_where}.description", "must be a non-empty string")
            artifact = output.get("artifact")
            if artifact is not None and not nonempty_string(artifact):
                add(errors, f"{output_where}.artifact", "must be a non-empty string when present")
            elif artifact is not None:
                normalized_artifact = normalize_artifact_path(artifact)
                if normalized_artifact is None:
                    add(errors, f"{output_where}.artifact", f"invalid explicit artifact path {artifact!r}")
                else:
                    if normalized_artifact != artifact:
                        add(errors, f"{output_where}.artifact", f"path must be normalized as {normalized_artifact!r}")
                    output_artifacts.append((node_id, normalized_artifact))

        consumes_by_node[node_id] = list(node.get("consumes", []))
        if not string_list(node.get("acceptance")) or not node["acceptance"]:
            add(errors, f"{where}.acceptance", "must be a non-empty string list")

        decomposition_bound = node.get("decomposition_bound")
        if decomposition_bound is not None:
            expected_bound_fields = {"policy", "name", "value", "source_proposal"}
            if not isinstance(decomposition_bound, dict) or set(decomposition_bound) != expected_bound_fields:
                add(errors, f"{where}.decomposition_bound", f"must contain exactly {sorted(expected_bound_fields)!r}")
            else:
                if decomposition_bound.get("policy") != "ranking-function-v1":
                    add(errors, f"{where}.decomposition_bound.policy", "must equal 'ranking-function-v1'")
                if not nonempty_string(decomposition_bound.get("name")):
                    add(errors, f"{where}.decomposition_bound.name", "must be non-empty")
                bound_value = decomposition_bound.get("value")
                if not isinstance(bound_value, int) or isinstance(bound_value, bool) or bound_value < 1:
                    add(errors, f"{where}.decomposition_bound.value", "must be a positive integer")
                source_proposal = decomposition_bound.get("source_proposal")
                if not isinstance(source_proposal, str) or not DIGEST_RE.fullmatch(source_proposal):
                    add(errors, f"{where}.decomposition_bound.source_proposal", "must be sha256:<64 lowercase hex>")

        budget = node.get("budget")
        if not isinstance(budget, dict):
            add(errors, f"{where}.budget", "must be an object")
        else:
            tokens = budget.get("tokens")
            if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0:
                add(errors, f"{where}.budget.tokens", "must be a positive integer")
            else:
                planned_tokens += tokens

        isolation = node.get("isolation")
        if isolation not in ISOLATION_MODES:
            add(errors, f"{where}.isolation", f"must be one of {sorted(ISOLATION_MODES)}")
        elif isolation == "shared-readonly" and scope.get("write"):
            add(errors, f"{where}.isolation", "shared-readonly nodes may not own repository writes")
        elif kind == "expand" and isolation != "coordinator":
            add(errors, f"{where}.isolation", "expansion nodes must use coordinator isolation")
        elif kind == "integrate" and isolation != "integration":
            add(errors, f"{where}.isolation", "integration nodes must use integration isolation")

        retry = node.get("retry")
        if not isinstance(retry, dict):
            add(errors, f"{where}.retry", "must be an object")
        else:
            attempts = retry.get("attempts")
            maximum = retry.get("max_attempts")
            if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0:
                add(errors, f"{where}.retry.attempts", "must be a non-negative integer")
            if maximum != 2:
                add(errors, f"{where}.retry.max_attempts", "must equal 2 (one retry)")
            if isinstance(attempts, int) and isinstance(maximum, int) and attempts > maximum:
                add(errors, f"{where}.retry", "attempts may not exceed max_attempts")
            failure_class = retry.get("last_failure_class")
            if failure_class is not None and failure_class not in {"contract", "context", "reasoning", "environment", "authority", "external"}:
                add(errors, f"{where}.retry.last_failure_class", "has an unknown failure class")

        runtime = node.get("runtime")
        if runtime is not None and not isinstance(runtime, dict):
            add(errors, f"{where}.runtime", "must be an object when present")
        elif isinstance(runtime, dict):
            if runtime.get("tokens_used") is not None and (
                not isinstance(runtime.get("tokens_used"), int)
                or isinstance(runtime.get("tokens_used"), bool)
                or runtime.get("tokens_used") < 0
            ):
                add(errors, f"{where}.runtime.tokens_used", "must be a non-negative integer")
            if status == "active" and not nonempty_string(runtime.get("heartbeat_at")):
                warnings.append(f"{where}.runtime: active node has no heartbeat_at")

        if kind == "expand":
            for field, values in (
                ("covers", node.get("covers", [])),
                ("scope.write", scope.get("write", [])),
                ("scope.artifacts", scope.get("artifacts", [])),
                ("scope.decisions", scope.get("decisions", [])),
                ("consumes", node.get("consumes", [])),
                ("outputs", raw_outputs),
            ):
                if values:
                    add(errors, f"{where}.{field}", "must be empty for an expansion node")

    if has_cycle(node_ids, dependency_edges):
        add(errors, "nodes.depends_on", "dependency graph contains a cycle")
    if has_cycle(node_ids, parent_edges):
        add(errors, "nodes.parent", "parent graph contains a cycle")

    for node_id, node in nodes.items():
        parent = node.get("parent")
        if parent in nodes and nodes[parent].get("kind") != "expand":
            add(errors, f"node {node_id}.parent", f"parent {parent} is not an expansion node")
        if node.get("kind") == "expand" and node.get("status") == "expanded" and len(children[node_id]) < 2:
            add(errors, f"node {node_id}", "an expanded node must have at least two direct children")

    for index, (left_owner, left_path, left_kind) in enumerate(path_owners):
        if left_kind == "artifact" and paths_overlap(left_path, "memory"):
            add(errors, "scope.ownership", f"node {left_owner} may not own coordinator-reserved shared memory path {left_path!r}")
        if left_kind == "artifact" and paths_overlap(left_path, "integrity"):
            add(errors, "scope.ownership", f"node {left_owner} may not own coordinator-reserved integrity path {left_path!r}")
        if left_kind == "artifact" and paths_overlap(left_path, "evidence/attestations") and nodes.get(left_owner, {}).get("kind") != "verify":
            add(errors, "scope.ownership", f"non-verifier node {left_owner} may not own runner attestation path {left_path!r}")
        for right_owner, right_path, right_kind in path_owners[index + 1 :]:
            if left_owner != right_owner and paths_overlap(left_path, right_path):
                add(
                    errors,
                    "scope.ownership",
                    f"nodes {left_owner} ({left_kind}) and {right_owner} ({right_kind}) overlap at {left_path!r} / {right_path!r}",
                )

    for node_id, artifact in output_artifacts:
        if not any(paths_overlap(owner, artifact) and len(PurePosixPath(owner).parts) <= len(PurePosixPath(artifact).parts) for owner in owned_paths_by_node[node_id]):
            add(errors, f"node {node_id}.outputs", f"artifact {artifact!r} is outside the node's write and artifact scopes")

    for requirement_id, owners in coverage.items():
        if len(owners) > 1:
            add(errors, "coverage", f"requirement {requirement_id} is claimed by {', '.join(owners)}")
    uncovered = [requirement_id for requirement_id in requirements if not coverage.get(requirement_id)]
    if uncovered:
        message = f"uncovered requirements: {', '.join(uncovered)}"
        if phase in {"executable", "complete"}:
            add(errors, "coverage", message)
        else:
            warnings.append(f"coverage: {message}")

    if phase in {"executable", "complete"}:
        unexpanded = [
            node_id
            for node_id, node in nodes.items()
            if node.get("kind") == "expand" and node.get("status") != "expanded"
        ]
        if unexpanded:
            add(errors, "expansion", f"nodes not expanded: {', '.join(unexpanded)}")

        if intent_required is True and intent_status != "approved":
            add(errors, "intent_baseline.status", "must be approved before executable work")

    prototype_nodes = {node_id for node_id, node in nodes.items() if "prototyping" in node.get("operations", [])}
    if intent_required is True:
        if not prototype_nodes:
            add(errors, "intent_baseline", "required baseline needs a prototyping node")
        if phase in {"executable", "complete"}:
            incomplete_prototypes = [node_id for node_id in prototype_nodes if nodes[node_id].get("status") != "complete"]
            if incomplete_prototypes:
                add(errors, "intent_baseline", f"prototype nodes not complete: {', '.join(sorted(incomplete_prototypes))}")
        for node_id, node in nodes.items():
            if node_id in prototype_nodes or not ({"implementation", "integration"} & set(node.get("operations", []))):
                continue
            if not (prototype_nodes & dependency_ancestors(node_id, dependencies)):
                add(errors, f"node {node_id}.depends_on", "implementation/integration must descend from the approved prototype")

    for node_id, node in nodes.items():
        status = node.get("status")
        kind = node.get("kind")
        incomplete_dependencies = [
            dependency
            for dependency in dependencies.get(node_id, [])
            if nodes.get(dependency, {}).get("status") != "complete"
        ]
        if kind != "expand" and status in DEPENDENCY_GATED_STATUSES and incomplete_dependencies:
            add(
                errors,
                f"node {node_id}.status",
                f"{status} node has incomplete dependencies: {', '.join(incomplete_dependencies)}",
            )

    if phase == "complete":
        incomplete_nodes = [
            node_id
            for node_id, node in nodes.items()
            if node.get("kind") != "expand" and node.get("status") != "complete"
        ]
        if incomplete_nodes:
            add(errors, "completion", f"nodes not complete: {', '.join(incomplete_nodes)}")
        if not isinstance(lifecycle, dict) or lifecycle.get("status") != "complete":
            add(errors, "lifecycle.status", "must be complete in complete phase")

        for requirement_id in requirements:
            owned_claims = primary_claims.get(requirement_id, [])
            if len(owned_claims) != 1:
                add(errors, "verification.claims", f"requirement {requirement_id} needs exactly one primary claim")
            elif owned_claims[0].get("state") != "verified":
                add(errors, "verification.claims", f"required claim {requirement_id} must be verified")
        limited = any(claim.get("requirement_id") is None and claim.get("state") != "verified" for claim in claims)
        expected_outcome = "complete_with_limits" if limited else "verified"
        if verification_outcome != expected_outcome:
            add(errors, "verification.outcome", f"must be {expected_outcome} for the recorded claims")

    verifier_owned_paths = [
        path
        for node_id, paths in owned_paths_by_node.items()
        if nodes.get(node_id, {}).get("kind") == "verify"
        for path in paths
    ]
    for where, artifact in claim_evidence_paths:
        if not any(paths_overlap(owner, artifact) for owner in verifier_owned_paths):
            add(errors, f"{where}.evidence", f"artifact {artifact!r} must be owned by a verify node")

    for node_id, consumed_outputs in consumes_by_node.items():
        ancestors = dependency_ancestors(node_id, dependencies)
        for output_id in consumed_outputs:
            producer = outputs.get(output_id)
            if producer is None:
                add(errors, f"node {node_id}.consumes", f"unknown output {output_id}")
            elif producer not in ancestors:
                add(errors, f"node {node_id}.consumes", f"output {output_id} from {producer} is not a dependency ancestor")

    if token_budget is not None and planned_tokens > token_budget:
        add(errors, "budget", f"planned {planned_tokens} tokens exceeds limit {token_budget}")

    for node_id, node in nodes.items():
        if node.get("kind") == "expand" or node.get("status") != "pending":
            continue
        if all(nodes.get(dependency, {}).get("status") == "complete" for dependency in dependencies.get(node_id, [])):
            ready.append(node_id)
    ready.sort()
    if max_parallel is not None and len(ready) > max_parallel:
        warnings.append(
            f"ready: {len(ready)} nodes are ready but max_parallel is {max_parallel}; dispatch only {max_parallel}"
        )

    return errors, warnings, ready


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", help="Path to graph.json")
    parser.add_argument("--phase", choices=("draft", "executable", "complete"), default="draft")
    parser.add_argument("--ready", action="store_true", help="Print ready node IDs")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON")
    args = parser.parse_args()

    try:
        with open(args.graph, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR graph: {exc}", file=sys.stderr)
        return 2

    errors, warnings, ready = validate(data, args.phase)
    if args.as_json:
        print(json.dumps({"valid": not errors, "errors": errors, "warnings": warnings, "ready": ready}, indent=2))
    else:
        for warning in warnings:
            print(f"WARNING {warning}")
        for error in errors:
            print(f"ERROR {error}")
        if not errors:
            print(f"VALID {args.phase} workflow graph")
        if args.ready:
            print("READY " + (" ".join(ready) if ready else "(none)"))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
