#!/usr/bin/env python3
"""Publish one verified Graphflow tree through the repository's Ship contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from executor_common import append_event, atomic_json, canonical_graph_digest, json_digest, load_json, now_utc
import evidence_runner
import workspace_manager


ADAPTER = "ship-v1"
CAPABILITIES = ["commit", "push", "pull_request", "network", "credentials"]
STATUSES = {"not_required", "proposed", "waiting_approval", "publishing", "waiting_external", "published", "blocked"}
DELIVERY_FIELDS = {
    "schema_version", "required", "adapter", "status", "remote", "base_branch", "head_branch",
    "record", "commit", "pull_request", "required_capabilities", "grant", "manifest", "proof",
    "request_id", "failure", "updated_at",
}
RECORD_FIELDS = {"mode", "active_plan", "completed_plan", "no_plan_reason"}
COMMIT_FIELDS = {"subject", "body"}
PR_FIELDS = {"title", "body"}
GRANT_FIELDS = {"capabilities", "request_id", "request_digest", "granted_at"}
MANIFEST_FIELDS = {
    "schema_version", "workflow_id", "adapter", "graph_digest", "remote", "base_branch", "base_sha",
    "head_branch", "verified_sha", "verified_tree", "verification", "record", "commit", "pull_request", "prepared_at",
}
VERIFICATION_FIELDS = {"plan_digest", "runner_digest", "contract_digest", "attestations_digest", "external_gate_digest"}
PROOF_FIELDS = {
    "schema_version", "workflow_id", "adapter", "manifest_digest", "base_sha", "verified_sha",
    "verified_tree", "release_sha", "release_tree", "remote_base_sha", "remote_head_sha", "pr_url",
    "pr_state", "published_at",
}
SAFE_REF = re.compile(r"^(?![./])(?!.*(?:\.\.|//|@\{|\\|[~^:?*\[]))(?!.*[./]$)[A-Za-z0-9._/-]+$")
SUBJECT = re.compile(r"^(?:feat|fix|docs|chore|refactor|test|perf)(?:\([a-z0-9._-]+\))?: [a-z0-9][^\n.]{2,70}$")
SHA = re.compile(r"^[0-9a-f]{40,64}$")


class ReprepareRequired(ValueError):
    """The approved surface is no longer current and needs a fresh approval."""


def default_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "required": False,
        "adapter": ADAPTER,
        "status": "not_required",
        "remote": None,
        "base_branch": None,
        "head_branch": None,
        "record": {"mode": "not_applicable", "active_plan": None, "completed_plan": None, "no_plan_reason": None},
        "commit": None,
        "pull_request": None,
        "required_capabilities": [],
        "grant": None,
        "manifest": "runtime/delivery/manifest.json",
        "proof": "runtime/delivery/proof.json",
        "request_id": None,
        "failure": None,
        "updated_at": None,
    }


def run(
    repo: Path,
    argv: list[str],
    *,
    check: bool = True,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(argv, cwd=repo, input=input_text, capture_output=True, text=True, check=False, env=env)
    if check and completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(detail or f"command failed with exit {completed.returncode}")
    return completed


def git(repo: Path, *args: str, check: bool = True, input_text: str | None = None, env: dict[str, str] | None = None) -> str:
    return run(repo, ["git", *args], check=check, input_text=input_text, env=env).stdout.strip()


def relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts or "\\" in value:
        raise ValueError(f"delivery {label} must be a safe relative path")
    return value


def validate_config(value: Any, workflow_id: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != DELIVERY_FIELDS:
        raise ValueError(f"runtime.delivery must contain exactly {sorted(DELIVERY_FIELDS)!r}")
    if value.get("schema_version") != 1 or not isinstance(value.get("required"), bool) or value.get("adapter") != ADAPTER:
        raise ValueError("runtime.delivery has invalid schema, required flag, or adapter")
    if value.get("status") not in STATUSES:
        raise ValueError("runtime.delivery status is invalid")
    if value.get("manifest") != "runtime/delivery/manifest.json" or value.get("proof") != "runtime/delivery/proof.json":
        raise ValueError("runtime.delivery must use canonical manifest and proof paths")
    if value["required"] is False:
        expected_null = ("remote", "base_branch", "head_branch", "commit", "pull_request", "grant", "request_id", "failure")
        if value["status"] != "not_required" or value.get("required_capabilities") != [] or any(value.get(key) is not None for key in expected_null):
            raise ValueError("optional delivery must be not_required with no authority or publish target")
        if value.get("record") != {"mode": "not_applicable", "active_plan": None, "completed_plan": None, "no_plan_reason": None}:
            raise ValueError("optional delivery must use a not_applicable record contract")
        return value
    if value["status"] == "not_required":
        raise ValueError("required delivery may not use not_required status")
    for field in ("remote", "base_branch", "head_branch"):
        item = value.get(field)
        if not isinstance(item, str) or not SAFE_REF.fullmatch(item):
            raise ValueError(f"runtime.delivery.{field} is not a safe Git name")
    if value["remote"] != "origin" or value["base_branch"] != "master":
        raise ValueError("ship-v1 publishes only through origin with master as the PR base")
    if value["head_branch"] == value["base_branch"]:
        raise ValueError("delivery head branch must differ from the base branch")
    record = value.get("record")
    if not isinstance(record, dict) or set(record) != RECORD_FIELDS or record.get("mode") not in {"no_plan", "completed_plan"}:
        raise ValueError("runtime.delivery.record is invalid")
    if record["mode"] == "no_plan":
        if record.get("active_plan") is not None or record.get("completed_plan") is not None or not isinstance(record.get("no_plan_reason"), str) or not record["no_plan_reason"].strip():
            raise ValueError("no_plan delivery needs a concrete reason and no plan paths")
    else:
        relative_path(record.get("active_plan"), "record.active_plan")
        relative_path(record.get("completed_plan"), "record.completed_plan")
        if record.get("no_plan_reason") is not None:
            raise ValueError("completed_plan delivery may not include a no-plan reason")
    commit = value.get("commit")
    if not isinstance(commit, dict) or set(commit) != COMMIT_FIELDS or not isinstance(commit.get("subject"), str) or not SUBJECT.fullmatch(commit["subject"]):
        raise ValueError("runtime.delivery.commit must contain a conventional English subject")
    if not isinstance(commit.get("body"), str) or not commit["body"].strip() or "\x00" in commit["body"]:
        raise ValueError("runtime.delivery.commit.body must be non-empty")
    pull_request = value.get("pull_request")
    if not isinstance(pull_request, dict) or set(pull_request) != PR_FIELDS:
        raise ValueError("runtime.delivery.pull_request is invalid")
    if pull_request.get("title") != commit["subject"]:
        raise ValueError("pull request title must equal the commit subject")
    body = pull_request.get("body")
    if not isinstance(body, str) or any(heading not in body for heading in ("## Goal", "## What changed", "## Verification")):
        raise ValueError("pull request body must follow the Ship headings")
    if value.get("required_capabilities") != CAPABILITIES:
        raise ValueError(f"delivery requires the exact Ship capabilities {CAPABILITIES!r}")
    grant = value.get("grant")
    if grant is not None and (not isinstance(grant, dict) or set(grant) != GRANT_FIELDS or grant.get("capabilities") != CAPABILITIES):
        raise ValueError("runtime.delivery.grant is invalid")
    if isinstance(grant, dict) and grant.get("request_id") != value.get("request_id"):
        raise ValueError("runtime.delivery grant/request identity mismatch")
    for field in ("request_id", "failure", "updated_at"):
        if value.get(field) is not None and not isinstance(value[field], str):
            raise ValueError(f"runtime.delivery.{field} must be null or a string")
    return value


def load_runtime(workflow_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    graph = load_json(workflow_dir / "graph.json", "graph")
    runtime = load_json(workflow_dir / "runtime.json", "runtime")
    if not isinstance(graph, dict) or not isinstance(runtime, dict) or runtime.get("workflow_id") != graph.get("workflow_id"):
        raise ValueError("delivery workflow/runtime identity mismatch")
    delivery = validate_config(runtime.get("delivery"), str(graph.get("workflow_id")))
    return graph, runtime, delivery


def assert_graph_complete(graph: dict[str, Any]) -> None:
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict) and node.get("kind") != "expand"]
    verification = graph.get("verification") if isinstance(graph.get("verification"), dict) else {}
    if graph.get("lifecycle", {}).get("status") != "complete" or not nodes or any(node.get("status") != "complete" for node in nodes):
        raise ValueError("Ship delivery requires a locally complete workflow graph")
    if verification.get("outcome") not in {"verified", "complete_with_limits"}:
        raise ValueError("Ship delivery requires calibrated final verification")


def save_runtime(workflow_dir: Path, runtime: dict[str, Any], delivery: dict[str, Any]) -> None:
    delivery["updated_at"] = now_utc()
    runtime["delivery"] = delivery
    atomic_json(workflow_dir / "runtime.json", runtime)
    append_event(
        workflow_dir / "runtime" / "delivery" / "events.jsonl",
        {"at": delivery["updated_at"], "status": delivery["status"], "failure": delivery.get("failure")},
    )


def verified_source(workflow_dir: Path, repo_root: Path) -> tuple[Path, str, str, str]:
    registry = workspace_manager.load_registry(workflow_dir)
    verifiers = [entry for entry in registry["entries"].values() if isinstance(entry, dict) and entry.get("mode") == "verifier"]
    if not verifiers or any(entry.get("status") != "verified" for entry in verifiers):
        raise ValueError("delivery requires every registered verifier workspace to be verified")
    source_refs = {entry.get("source_ref") for entry in verifiers}
    if len(source_refs) != 1 or not isinstance(next(iter(source_refs)), str):
        raise ValueError("verifiers must attest one integration workspace")
    source_ref = str(next(iter(source_refs)))
    source = registry["entries"].get(source_ref)
    if not isinstance(source, dict) or not isinstance(source.get("checkpoint_sha"), str) or not isinstance(source.get("base_sha"), str):
        raise ValueError("delivery integration checkpoint is missing")
    verified_sha = source["checkpoint_sha"]
    base_sha = source["base_sha"]
    verifier_heads = {entry.get("head_sha") for entry in verifiers}
    if verifier_heads != {verified_sha}:
        raise ValueError("verifier HEAD does not match the integration checkpoint")
    verifier_path = Path(str(verifiers[0].get("path"))).resolve()
    workspace_manager.validate_entry(repo_root, registry, verifiers[0], require_clean=True)
    ancestor = run(verifier_path, ["git", "merge-base", "--is-ancestor", base_sha, verified_sha], check=False)
    if ancestor.returncode:
        raise ValueError("verified checkpoint is not descended from its pinned base")
    verified_tree = git(verifier_path, "rev-parse", f"{verified_sha}^{{tree}}")
    return verifier_path, base_sha, verified_sha, verified_tree


def validate_record(root: Path, record: dict[str, Any]) -> None:
    if record["mode"] == "no_plan":
        return
    active = root / record["active_plan"]
    completed = root / record["completed_plan"]
    if active.exists() or not completed.is_file():
        raise ValueError("Ship Record is incomplete: active plan remains or completed plan is missing")
    text = completed.read_text(encoding="utf-8")
    if not re.search(r"^## Outcome \(\d{4}-\d{2}-\d{2}\)$", text, re.MULTILINE):
        raise ValueError("completed plan is missing the Ship Outcome section")


def manifest_value(
    workflow_dir: Path, verifier_path: Path, graph: dict[str, Any], delivery: dict[str, Any], base_sha: str, verified_sha: str, verified_tree: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "workflow_id": graph["workflow_id"],
        "adapter": ADAPTER,
        "graph_digest": canonical_graph_digest(graph),
        "remote": delivery["remote"],
        "base_branch": delivery["base_branch"],
        "base_sha": base_sha,
        "head_branch": delivery["head_branch"],
        "verified_sha": verified_sha,
        "verified_tree": verified_tree,
        "verification": verification_binding(workflow_dir, verifier_path, require_complete=True),
        "record": delivery["record"],
        "commit": delivery["commit"],
        "pull_request": delivery["pull_request"],
        "prepared_at": now_utc(),
    }


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verification_binding(workflow_dir: Path, repo_root: Path | None = None, *, require_complete: bool = False) -> dict[str, Any]:
    plan = load_json(workflow_dir / "integrity" / "verification-plan.json", "verification plan")
    lock = load_json(workflow_dir / "integrity" / "lock.json", "integrity lock")
    if not isinstance(plan, dict) or not isinstance(lock, dict) or lock.get("status") != "locked":
        raise ValueError("Ship delivery requires a locked verification plan")
    if require_complete:
        if repo_root is None:
            raise ValueError("Ship delivery needs the verified repository for proof validation")
        evidence_runner.command_validate(workflow_dir, repo_root, "complete")
    records: list[dict[str, str]] = []
    for directory in (workflow_dir / "evidence" / "attestations", workflow_dir / "integrity" / "reviews"):
        if directory.is_dir():
            records.extend(
                {"path": path.relative_to(workflow_dir).as_posix(), "digest": file_digest(path)}
                for path in sorted(directory.rglob("*.json")) if path.is_file()
            )
    if not records:
        raise ValueError("Ship delivery requires current attestation and review artifacts")
    external = plan.get("external_gate") if isinstance(plan.get("external_gate"), dict) else {}
    external_digest = None
    if external.get("required") is True:
        artifact = external.get("artifact")
        path = workflow_dir / artifact if isinstance(artifact, str) else None
        if path is None or not path.is_file() or file_digest(path) != external.get("digest"):
            raise ValueError("Ship delivery external-gate evidence is missing or stale")
        external_digest = external["digest"]
    value = {
        "plan_digest": lock.get("plan_digest"),
        "runner_digest": lock.get("runner_digest"),
        "contract_digest": lock.get("contract_digest"),
        "attestations_digest": json_digest(records),
        "external_gate_digest": external_digest,
    }
    if set(value) != VERIFICATION_FIELDS or any(not isinstance(value[field], str) for field in ("plan_digest", "runner_digest", "contract_digest", "attestations_digest")):
        raise ValueError("Ship verification binding is invalid")
    return value


def request_digest(question: str, alternatives: list[str], risks: list[str], triage: dict[str, Any]) -> str:
    surface = json.dumps(
        {"question": question, "alternatives": alternatives, "risks": risks, "triage": triage},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(surface).hexdigest()


def prepare(workflow_dir: Path, repo_root: Path) -> dict[str, Any]:
    graph, runtime, delivery = load_runtime(workflow_dir)
    if not delivery["required"]:
        return {"status": "not_required"}
    assert_graph_complete(graph)
    verifier_path, base_sha, verified_sha, verified_tree = verified_source(workflow_dir, repo_root)
    validate_record(verifier_path, delivery["record"])
    manifest = manifest_value(workflow_dir, verifier_path, graph, delivery, base_sha, verified_sha, verified_tree)
    manifest_path = workflow_dir / delivery["manifest"]
    previous = load_json(manifest_path, "delivery manifest") if manifest_path.is_file() else None
    if isinstance(previous, dict):
        comparable = dict(previous)
        comparable["prepared_at"] = manifest["prepared_at"]
        if comparable == manifest:
            manifest = previous
    if set(manifest) != MANIFEST_FIELDS:
        raise ValueError("delivery manifest shape is invalid")
    atomic_json(manifest_path, manifest)
    manifest_digest = json_digest(manifest)
    triage = {
        "blocking_scope": "workflow",
        "impacts": ["irreversible_action"],
        "affected_nodes": [],
        "no_safe_default_reason": "Ship Publish mutates a remote branch and pull-request state.",
        "resolution_mode": "resume",
        "request_graph_digest": manifest["graph_digest"],
        "authority_capabilities": CAPABILITIES,
        "delivery_manifest_digest": manifest_digest,
        "commit_subject": manifest["commit"]["subject"],
        "commit_body": manifest["commit"]["body"],
        "pull_request_title": manifest["pull_request"]["title"],
        "pull_request_body": manifest["pull_request"]["body"],
    }
    question = (
        f"Publish verified tree {verified_tree[:12]} to {delivery['remote']}/{delivery['head_branch']} "
        f"and open PR '{delivery['pull_request']['title']}' against {delivery['base_branch']}?"
    )
    alternatives = ["Approve this exact Ship manifest", "Reject and retain the verified local checkpoint"]
    risks = [
        "Push mutates the configured remote branch.",
        "Pull-request creation is externally visible.",
        "Base-branch drift will stop publication and require reintegration.",
    ]
    digest = request_digest(question, alternatives, risks, triage)
    request_id = f"delivery-publish-{digest.removeprefix('sha256:')[:12]}"
    request_path = workflow_dir / "runtime" / "requests" / f"{request_id}.json"
    request = {
        "schema_version": 2,
        "broker": "delivery",
        "request_id": request_id,
        "node_id": None,
        "digest": digest,
        "question": question,
        "alternatives": alternatives,
        "risks": risks,
        "triage": triage,
        "status": "pending",
        "created_at": now_utc(),
        "response": None,
    }
    if request_path.is_file():
        existing = load_json(request_path, "delivery request")
        if not isinstance(existing, dict) or existing.get("digest") != digest:
            raise ValueError("delivery request ID collision")
    else:
        atomic_json(request_path, request)
    delivery.update(status="waiting_approval", request_id=request_id, failure=None, grant=None)
    save_runtime(workflow_dir, runtime, delivery)
    return {"status": "waiting_approval", "request_id": request_id, "manifest_digest": manifest_digest}


def exact_grant(workflow_dir: Path, delivery: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    request_id = delivery.get("request_id")
    if not isinstance(request_id, str):
        raise ValueError("delivery request is missing")
    request = load_json(workflow_dir / "runtime" / "requests" / f"{request_id}.json", "delivery request")
    status = request.get("status") if isinstance(request, dict) else None
    recoverable_consumed = status == "consumed" and (workflow_dir / delivery["proof"]).is_file()
    if not isinstance(request, dict) or status not in {"approved", "consumed"} or (status == "consumed" and not recoverable_consumed) or request.get("broker") != "delivery":
        raise ValueError("delivery publish still requires approval")
    triage = request.get("triage") if isinstance(request.get("triage"), dict) else {}
    if triage.get("delivery_manifest_digest") != json_digest(manifest) or triage.get("request_graph_digest") != manifest.get("graph_digest"):
        raise ValueError("delivery approval is stale for the current manifest")
    grant = delivery.get("grant")
    if not isinstance(grant, dict) or grant.get("request_id") != request_id or grant.get("request_digest") != request.get("digest") or grant.get("capabilities") != CAPABILITIES:
        raise ValueError("delivery authority grant is missing or stale")
    return request


def commit_env(prepared_at: str) -> dict[str, str]:
    value = os.environ.copy()
    value.update({
        "GIT_AUTHOR_NAME": "Graphflow Ship Broker",
        "GIT_AUTHOR_EMAIL": "graphflow@local.invalid",
        "GIT_COMMITTER_NAME": "Graphflow Ship Broker",
        "GIT_COMMITTER_EMAIL": "graphflow@local.invalid",
        "GIT_AUTHOR_DATE": prepared_at,
        "GIT_COMMITTER_DATE": prepared_at,
    })
    return value


def release_commit(repo: Path, manifest: dict[str, Any]) -> str:
    message = manifest["commit"]["subject"] + "\n\n" + manifest["commit"]["body"].strip() + "\n"
    release_sha = git(
        repo, "commit-tree", manifest["verified_tree"], "-p", manifest["base_sha"],
        input_text=message, env=commit_env(manifest["prepared_at"]),
    )
    if not SHA.fullmatch(release_sha) or git(repo, "rev-parse", f"{release_sha}^{{tree}}") != manifest["verified_tree"]:
        raise ValueError("release commit does not preserve the verified tree")
    return release_sha


def ls_remote(repo: Path, remote: str, branch: str) -> str | None:
    output = git(repo, "ls-remote", "--heads", remote, f"refs/heads/{branch}")
    if not output:
        return None
    fields = output.split()
    if len(fields) != 2 or fields[1] != f"refs/heads/{branch}" or not SHA.fullmatch(fields[0]):
        raise ValueError("remote ref response is invalid")
    return fields[0]


def gh_json(repo: Path, gh_bin: str, args: list[str]) -> Any:
    completed = run(repo, [gh_bin, *args])
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("gh returned invalid JSON") from error


def publish(workflow_dir: Path, repo_root: Path, gh_bin: str) -> dict[str, Any]:
    graph, runtime, delivery = load_runtime(workflow_dir)
    assert_graph_complete(graph)
    manifest_path = workflow_dir / delivery["manifest"]
    manifest = load_json(manifest_path, "delivery manifest")
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS or manifest.get("workflow_id") != graph.get("workflow_id"):
        raise ValueError("delivery manifest is missing or invalid")
    exact_grant(workflow_dir, delivery, manifest)
    verifier_path, base_sha, verified_sha, verified_tree = verified_source(workflow_dir, repo_root)
    if (base_sha, verified_sha, verified_tree, canonical_graph_digest(graph)) != (
        manifest["base_sha"], manifest["verified_sha"], manifest["verified_tree"], manifest["graph_digest"],
    ):
        raise ReprepareRequired("delivery source changed after approval")
    if verification_binding(workflow_dir, verifier_path, require_complete=True) != manifest["verification"]:
        raise ReprepareRequired("verification evidence changed after approval")
    delivery.update(status="publishing", failure=None)
    save_runtime(workflow_dir, runtime, delivery)
    remote_base = ls_remote(verifier_path, manifest["remote"], manifest["base_branch"])
    if remote_base != manifest["base_sha"]:
        delivery.update(status="waiting_external", failure="Remote base moved after verification; rebase, reintegrate, and verify a new tree.")
        save_runtime(workflow_dir, runtime, delivery)
        return {"status": "waiting_external", "failure": delivery["failure"]}
    release_sha = release_commit(verifier_path, manifest)
    remote_head = ls_remote(verifier_path, manifest["remote"], manifest["head_branch"])
    if remote_head not in {None, release_sha}:
        delivery.update(status="waiting_external", failure="Remote delivery branch exists at another SHA; force push is forbidden.")
        save_runtime(workflow_dir, runtime, delivery)
        return {"status": "waiting_external", "failure": delivery["failure"]}
    if remote_head is None:
        git(
            verifier_path,
            "push",
            "--atomic",
            manifest["remote"],
            f"{manifest['base_sha']}:refs/heads/{manifest['base_branch']}",
            f"{release_sha}:refs/heads/{manifest['head_branch']}",
        )
    remote_head = ls_remote(verifier_path, manifest["remote"], manifest["head_branch"])
    if remote_head != release_sha:
        raise ValueError("remote branch proof does not match the release commit")
    if ls_remote(verifier_path, manifest["remote"], manifest["base_branch"]) != manifest["base_sha"]:
        raise ValueError("remote base moved during atomic publication; pull-request creation is blocked")
    run(verifier_path, [gh_bin, "auth", "status"])
    query = [
        "pr", "list", "--head", manifest["head_branch"], "--base", manifest["base_branch"], "--state", "all",
        "--json", "url,state,headRefOid,title,body,baseRefName,headRefName",
    ]
    prs = gh_json(verifier_path, gh_bin, query)
    if not isinstance(prs, list):
        raise ValueError("gh pr list returned an invalid result")
    matching = [item for item in prs if isinstance(item, dict) and item.get("headRefName") == manifest["head_branch"] and item.get("baseRefName") == manifest["base_branch"]]
    if len(matching) > 1:
        raise ValueError("multiple pull requests match the delivery branch")
    if matching:
        pr = matching[0]
        if pr.get("headRefOid") != release_sha:
            raise ValueError("existing pull request does not point to the release commit")
        if pr.get("state") == "CLOSED":
            raise ValueError("matching pull request is closed without proof of merge")
        pr_url = pr.get("url")
        if pr.get("title") != manifest["pull_request"]["title"] or pr.get("body") != manifest["pull_request"]["body"]:
            run(
                verifier_path,
                [gh_bin, "pr", "edit", str(pr_url), "--title", manifest["pull_request"]["title"], "--body", manifest["pull_request"]["body"]],
            )
    else:
        run(
            verifier_path,
            [
                gh_bin, "pr", "create", "--base", manifest["base_branch"], "--head", manifest["head_branch"],
                "--title", manifest["pull_request"]["title"], "--body", manifest["pull_request"]["body"],
            ],
        )
    final_prs = gh_json(verifier_path, gh_bin, query)
    final_matching = [
        item for item in final_prs
        if isinstance(item, dict)
        and item.get("headRefName") == manifest["head_branch"]
        and item.get("baseRefName") == manifest["base_branch"]
    ] if isinstance(final_prs, list) else []
    if len(final_matching) != 1:
        raise ValueError("pull request remote proof is missing or ambiguous")
    final_pr = final_matching[0]
    pr_url = final_pr.get("url")
    if (
        not isinstance(pr_url, str) or not pr_url.startswith("https://")
        or final_pr.get("headRefOid") != release_sha
        or final_pr.get("state") not in {"OPEN", "MERGED"}
        or final_pr.get("title") != manifest["pull_request"]["title"]
        or final_pr.get("body") != manifest["pull_request"]["body"]
    ):
        raise ValueError("pull request remote proof does not match the Ship manifest")
    proof = {
        "schema_version": 1,
        "workflow_id": graph["workflow_id"],
        "adapter": ADAPTER,
        "manifest_digest": json_digest(manifest),
        "base_sha": manifest["base_sha"],
        "verified_sha": manifest["verified_sha"],
        "verified_tree": manifest["verified_tree"],
        "release_sha": release_sha,
        "release_tree": git(verifier_path, "rev-parse", f"{release_sha}^{{tree}}"),
        "remote_base_sha": remote_base,
        "remote_head_sha": remote_head,
        "pr_url": pr_url,
        "pr_state": final_pr["state"],
        "published_at": now_utc(),
    }
    if set(proof) != PROOF_FIELDS:
        raise ValueError("delivery proof shape is invalid")
    atomic_json(workflow_dir / delivery["proof"], proof)
    request_path = workflow_dir / "runtime" / "requests" / f"{delivery['request_id']}.json"
    request = load_json(request_path, "delivery request")
    request["status"] = "consumed"
    request["consumed_at"] = now_utc()
    atomic_json(request_path, request)
    delivery.update(status="published", grant=None, failure=None)
    save_runtime(workflow_dir, runtime, delivery)
    return {"status": "published", "release_sha": release_sha, "pr_url": pr_url, "proof": delivery["proof"]}


def validate_published(workflow_dir: Path, graph: dict[str, Any], delivery: dict[str, Any]) -> dict[str, Any]:
    manifest = load_json(workflow_dir / delivery["manifest"], "delivery manifest")
    proof = load_json(workflow_dir / delivery["proof"], "delivery proof")
    if (
        not isinstance(manifest, dict)
        or set(manifest) != MANIFEST_FIELDS
        or not isinstance(proof, dict)
        or set(proof) != PROOF_FIELDS
        or manifest.get("workflow_id") != graph.get("workflow_id")
        or proof.get("workflow_id") != graph.get("workflow_id")
        or proof.get("adapter") != ADAPTER
        or proof.get("manifest_digest") != json_digest(manifest)
        or manifest.get("graph_digest") != canonical_graph_digest(graph)
        or manifest.get("verification") != verification_binding(workflow_dir)
    ):
        raise ValueError("published delivery proof is invalid or stale")
    correlations = {
        "base_sha": manifest["base_sha"],
        "verified_sha": manifest["verified_sha"],
        "verified_tree": manifest["verified_tree"],
        "release_tree": manifest["verified_tree"],
        "remote_base_sha": manifest["base_sha"],
        "remote_head_sha": proof.get("release_sha"),
    }
    if any(proof.get(field) != expected for field, expected in correlations.items()):
        raise ValueError("published delivery proof does not correlate to the approved manifest")
    if (
        not isinstance(proof.get("release_sha"), str)
        or not SHA.fullmatch(proof["release_sha"])
        or not isinstance(proof.get("pr_url"), str)
        or not proof["pr_url"].startswith("https://")
        or proof.get("pr_state") not in {"OPEN", "MERGED"}
    ):
        raise ValueError("published delivery proof has invalid remote evidence")
    return proof


def advance(workflow_dir: Path, repo_root: Path, gh_bin: str | None = None) -> dict[str, Any]:
    graph, runtime, delivery = load_runtime(workflow_dir)
    if not delivery["required"]:
        return {"status": "not_required"}
    if delivery["status"] == "published":
        proof = validate_published(workflow_dir, graph, delivery)
        return {"status": "published", "release_sha": proof["release_sha"], "pr_url": proof["pr_url"], "proof": delivery["proof"]}
    if delivery["status"] == "proposed":
        return prepare(workflow_dir, repo_root)
    if delivery["status"] == "blocked":
        return {"status": "blocked", "failure": delivery.get("failure")}
    if delivery["status"] == "waiting_approval":
        request_id = delivery.get("request_id")
        request = load_json(workflow_dir / "runtime" / "requests" / f"{request_id}.json", "delivery request") if isinstance(request_id, str) else None
        if not isinstance(request, dict) or request.get("status") == "pending":
            return {"status": "waiting_approval", "request_id": request_id}
        if request.get("status") == "rejected":
            delivery.update(status="blocked", grant=None, failure="User rejected the exact Ship manifest.")
            save_runtime(workflow_dir, runtime, delivery)
            return {"status": "blocked", "failure": delivery["failure"]}
    binary = gh_bin or shutil.which("gh")
    if not binary:
        delivery.update(status="waiting_external", failure="gh is required for the Ship pull-request adapter.")
        save_runtime(workflow_dir, runtime, delivery)
        return {"status": "waiting_external", "failure": delivery["failure"]}
    try:
        return publish(workflow_dir, repo_root, binary)
    except ReprepareRequired as error:
        _, runtime, delivery = load_runtime(workflow_dir)
        previous_request_id = delivery.get("request_id")
        if isinstance(previous_request_id, str):
            request_path = workflow_dir / "runtime" / "requests" / f"{previous_request_id}.json"
            request = load_json(request_path, "delivery request")
            if isinstance(request, dict) and request.get("status") != "consumed":
                request["status"] = "superseded"
                request["superseded_at"] = now_utc()
                atomic_json(request_path, request)
        delivery.update(status="proposed", request_id=None, grant=None, failure=str(error)[:500])
        save_runtime(workflow_dir, runtime, delivery)
        return prepare(workflow_dir, repo_root)
    except ValueError as error:
        _, runtime, delivery = load_runtime(workflow_dir)
        delivery.update(status="waiting_external", failure=str(error)[:500])
        save_runtime(workflow_dir, runtime, delivery)
        return {"status": "waiting_external", "failure": delivery["failure"]}


def projection(workflow_dir: Path) -> dict[str, Any]:
    _, _, delivery = load_runtime(workflow_dir)
    return {
        "required": delivery["required"],
        "adapter": delivery["adapter"],
        "status": delivery["status"],
        "remote": delivery["remote"],
        "base_branch": delivery["base_branch"],
        "head_branch": delivery["head_branch"],
        "request_id": delivery["request_id"],
        "failure": delivery["failure"],
        "proof": delivery["proof"] if delivery["status"] == "published" else None,
        "updated_at": delivery["updated_at"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "advance", "inspect"):
        command = commands.add_parser(name)
        command.add_argument("workflow_dir", type=Path)
        if name != "inspect":
            command.add_argument("--repo-root", type=Path, required=True)
        if name == "advance":
            command.add_argument("--gh-bin")
    args = parser.parse_args()
    workflow_dir = args.workflow_dir.resolve()
    try:
        if args.command == "prepare":
            result = prepare(workflow_dir, args.repo_root.resolve())
        elif args.command == "advance":
            result = advance(workflow_dir, args.repo_root.resolve(), args.gh_bin)
        else:
            result = projection(workflow_dir)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
