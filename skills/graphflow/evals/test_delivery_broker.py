#!/usr/bin/env python3
"""Integration tests for the coordinator-owned Ship delivery broker."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "workflow-template"
CONFIRM = ROOT / "scripts" / "confirm_workflow.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("graphflow_delivery", ROOT / "scripts" / "delivery_broker.py")
assert SPEC and SPEC.loader
DELIVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DELIVERY)
import workspace_manager as WORKSPACES
import evidence_runner as EVIDENCE
import decomposition_broker as DECOMPOSITION
import run_workflow as WORKFLOW_RUNTIME
import question_gate as QUESTION_GATE
from skills.graphflow.evals.fixture_support import approve_manifest, complete_clear_review


def command(repo: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if check and completed.returncode:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.stdout.strip()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class DeliveryBrokerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.remote = self.root / "remote.git"
        self.workflow = self.root / "workflow"
        self.repo.mkdir()
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "master", str(self.repo)], check=True)
        command(self.repo, "config", "user.name", "Graphflow Eval")
        command(self.repo, "config", "user.email", "eval@graphflow.invalid")
        integration_file = self.repo / "apps/server/src/publish/bulk-retry.integration.ts"
        integration_file.parent.mkdir(parents=True, exist_ok=True)
        integration_file.write_text("base\n", encoding="utf-8")
        command(self.repo, "add", ".")
        command(self.repo, "commit", "-qm", "chore: base")
        hosting_url = "https://example.invalid/acme/portable-repo.git"
        command(self.repo, "config", f"url.{self.remote}.insteadOf", hosting_url)
        command(self.repo, "remote", "add", "origin", hosting_url)
        command(self.repo, "push", "-q", "origin", "master")
        shutil.copytree(TEMPLATE, self.workflow)

        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["lifecycle"]["status"] = "complete"
        graph["verification"] = {
            "outcome": "verified",
            "claims": [
                {
                    "id": f"C-{requirement['id']}",
                    "requirement_id": requirement["id"],
                    "statement": requirement["text"],
                    "state": "verified",
                    "confidence": "high",
                    "evidence": [{"check": "Ship release gate", "artifact": "evidence/attestations/CHK-SHIP-NEGATIVE.json"}],
                    "limitations": [],
                }
                for requirement in graph["objective"]["requirements"]
            ],
        }
        for node in graph["nodes"]:
            if node["kind"] != "expand":
                node["status"] = "complete"
        approve_manifest(self.workflow, graph)
        write_json(graph_path, graph)
        review_path = self.workflow / "question-review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        complete_clear_review(review)
        review["graph_digest"] = QUESTION_GATE.question_surface_digest(graph)
        review["reviewed_at"] = "2026-07-20T00:00:00Z"
        write_json(review_path, review)
        QUESTION_GATE.lock(self.workflow)
        requirement_ids = [requirement["id"] for requirement in graph["objective"]["requirements"]]
        plan = {
            "schema_version": 1,
            "workflow_id": graph["workflow_id"],
            "level": "medium",
            "checks": [
                {
                    "id": check_id,
                    "requirement_ids": requirement_ids,
                    "critical": True,
                    "class": check_class,
                    "argv": ["git", "diff", "--quiet", "HEAD", "HEAD"],
                    "cwd": "repo",
                    "env": {},
                    "expected_exit": 0,
                    "timeout_seconds": 30,
                    "watch": [{"root": "repo", "path": "apps/server/src/publish"}],
                    "attestation": f"evidence/attestations/{check_id}.json",
                    "verifier_node": "F",
                }
                for check_id, check_class in (("CHK-SHIP-NEGATIVE", "negative"), ("CHK-SHIP-BOUNDARY", "boundary"))
            ],
            "challenge_policy": {"required_classes": ["negative", "boundary"], "mutation_required": False},
            "separation_of_duties": {
                "producer_nodes": ["B", "C", "D", "E"],
                "verifier_nodes": ["F"],
                "min_independent_verifiers": 1,
            },
            "external_gate": {"required": False, "status": "not_required", "artifact": None, "digest": None, "provenance": None},
        }
        write_json(self.workflow / "integrity/verification-plan.json", plan)
        EVIDENCE.command_lock(self.workflow, self.repo)

        integration = WORKSPACES.provision_entry(self.workflow, self.repo, "workspace-e")
        integration_path = Path(integration["path"])
        before = WORKSPACES.snapshot(integration_path)
        changed = integration_path / "apps/server/src/publish/bulk-retry.integration.ts"
        changed.write_text("verified release tree\n", encoding="utf-8")
        node_e = next(node for node in graph["nodes"] if node["id"] == "E")
        scope = WORKSPACES.verify_scope(integration_path, node_e, before)
        WORKSPACES.checkpoint(self.workflow, "workspace-e", "E", scope)
        WORKSPACES.provision_entry(self.workflow, self.repo, "workspace-f")
        WORKSPACES.mark_status(self.workflow, "workspace-f", "verified")
        WORKSPACES.mark_status(self.workflow, "workspace-e", "integrated")
        for check_id in ("CHK-SHIP-NEGATIVE", "CHK-SHIP-BOUNDARY"):
            EVIDENCE.command_run(self.workflow, Path(WORKSPACES.load_registry(self.workflow)["entries"]["workspace-f"]["path"]), check_id)
        review_input = self.root / "review-input.json"
        write_json(
            review_input,
            {
                "schema_version": 1,
                "verifier_node": "F",
                "producer_nodes": ["B", "C", "D", "E"],
                "outcome": "pass",
                "challenge_classes": ["negative", "boundary"],
                "evidence_attestations": [
                    "evidence/attestations/CHK-SHIP-NEGATIVE.json",
                    "evidence/attestations/CHK-SHIP-BOUNDARY.json",
                ],
                "limitations": [],
            },
        )
        verifier_path = Path(WORKSPACES.load_registry(self.workflow)["entries"]["workspace-f"]["path"])
        EVIDENCE.command_record_review(self.workflow, verifier_path, review_input)
        EVIDENCE.command_validate(self.workflow, verifier_path, "complete")

        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["authority"]["network"] = True
        runtime["authority"]["credentials"] = True
        runtime["delivery"] = {
            "schema_version": 1,
            "required": True,
            "adapter": "ship-v1",
            "status": "proposed",
            "remote": "origin",
            "base_branch": "master",
            "head_branch": "graphflow/delivery-eval",
            "record": {"mode": "no_plan", "active_plan": None, "completed_plan": None, "no_plan_reason": "This bounded change has no plan file."},
            "commit": {"subject": "feat(server): publish verified tree", "body": "Land the verified Graphflow delivery-eval tree."},
            "pull_request": {
                "repository": "example.invalid/acme/portable-repo",
                "title": "feat(server): publish verified tree",
                "body": "## Goal\nPublish the verified tree.\n\n## What changed\n- Added the verified integration result.\n\n## Verification\n- Graphflow independent verifier passed.\n",
            },
            "required_capabilities": DELIVERY.CAPABILITIES,
            "grant": None,
            "manifest": "runtime/delivery/manifest.json",
            "proof": "runtime/delivery/proof.json",
            "request_id": None,
            "failure": None,
            "updated_at": None,
        }
        write_json(runtime_path, runtime)
        self.fake_gh = self.root / "fake-gh"
        gh_state = self.root / "fake-gh-state.json"
        self.fake_gh.write_text(
            "#!/usr/bin/env python3\n"
            "import json,subprocess,sys\n"
            "from pathlib import Path\n"
            "args=sys.argv[1:]\n"
            f"state=Path({str(gh_state)!r})\n"
            "if args[:2] == ['auth','status'] and '--hostname' in args: raise SystemExit(0)\n"
            "if args[:1] == ['pr'] and ('--repo' not in args or args[args.index('--repo')+1] != 'example.invalid/acme/portable-repo'): raise SystemExit(3)\n"
            "if args[:2] == ['pr','list']: print(state.read_text() if state.exists() else '[]'); raise SystemExit(0)\n"
            "if args[:2] == ['pr','create']:\n"
            " head=args[args.index('--head')+1]; base=args[args.index('--base')+1]\n"
            " title=args[args.index('--title')+1]; body=args[args.index('--body')+1]\n"
            " remote=subprocess.check_output(['git','remote'],text=True).splitlines()[0]\n"
            " out=subprocess.check_output(['git','ls-remote','--heads',remote,f'refs/heads/{head}'],text=True).split()[0]\n"
            " state.write_text(json.dumps([{'url':'https://example.invalid/pull/1','state':'OPEN','headRefOid':out,'title':title,'body':body,'baseRefName':base,'headRefName':head}]))\n"
            " print('https://example.invalid/pull/1'); raise SystemExit(0)\n"
            "if args[:2] == ['pr','edit']:\n"
            " data=json.loads(state.read_text()); data[0]['title']=args[args.index('--title')+1]; data[0]['body']=args[args.index('--body')+1]; state.write_text(json.dumps(data)); raise SystemExit(0)\n"
            "raise SystemExit(2)\n",
            encoding="utf-8",
        )
        self.fake_gh.chmod(0o700)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def delivery(self) -> dict:
        return json.loads((self.workflow / "runtime.json").read_text(encoding="utf-8"))["delivery"]

    def confirm(self) -> None:
        delivery = self.delivery()
        request = json.loads((self.workflow / "runtime/requests" / f"{delivery['request_id']}.json").read_text(encoding="utf-8"))
        completed = subprocess.run(
            [
                sys.executable, str(CONFIRM), str(self.workflow), "--request-id", request["request_id"],
                "--digest", request["digest"], "--decision", "approved", "--answer", "publish exact manifest",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def remote_ref(self, branch: str, remote: str = "origin") -> str | None:
        value = command(self.repo, "ls-remote", "--heads", remote, f"refs/heads/{branch}")
        return value.split()[0] if value else None

    def test_publish_is_manifest_bound_tree_exact_and_idempotent(self) -> None:
        prepared = DELIVERY.prepare(self.workflow, self.repo)
        self.assertEqual(prepared["status"], "waiting_approval")
        self.assertIsNone(self.remote_ref("graphflow/delivery-eval"))
        self.assertFalse((self.workflow / "runtime/delivery/proof.json").exists())
        self.confirm()

        published = DELIVERY.advance(self.workflow, self.repo, str(self.fake_gh))
        self.assertEqual(published["status"], "published")
        proof = json.loads((self.workflow / "runtime/delivery/proof.json").read_text(encoding="utf-8"))
        manifest = json.loads((self.workflow / "runtime/delivery/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(proof["release_tree"], manifest["verified_tree"])
        self.assertEqual(command(self.repo, "rev-parse", f"{proof['release_sha']}^"), manifest["base_sha"])
        self.assertEqual(self.remote_ref("graphflow/delivery-eval"), proof["release_sha"])
        self.assertEqual(self.delivery()["status"], "published")
        self.assertIsNone(self.delivery()["grant"])
        self.assertEqual(DELIVERY.advance(self.workflow, self.repo, "/missing/gh"), published)

    def test_github_auth_preflight_blocks_before_remote_push(self) -> None:
        prepared = DELIVERY.prepare(self.workflow, self.repo)
        self.assertEqual(prepared["status"], "waiting_approval")
        self.confirm()
        failing_gh = self.root / "failing-gh"
        trace = self.root / "failing-gh-args.json"
        failing_gh.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "from pathlib import Path\n"
            f"Path({str(trace)!r}).write_text(json.dumps(sys.argv[1:]))\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )
        failing_gh.chmod(0o700)

        outcome = DELIVERY.advance(self.workflow, self.repo, str(failing_gh))

        self.assertEqual(outcome["status"], "waiting_external")
        self.assertIn("preflight failed", outcome["failure"])
        self.assertEqual(json.loads(trace.read_text(encoding="utf-8"))[:3], ["auth", "status", "--hostname"])
        self.assertIsNone(self.remote_ref("graphflow/delivery-eval"))

    def test_preflight_does_not_touch_gh_without_network_and_credential_authority(self) -> None:
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["authority"]["network"] = False
        runtime["authority"]["credentials"] = False
        write_json(runtime_path, runtime)
        marker = self.root / "gh-invoked"
        forbidden_gh = self.root / "forbidden-gh"
        forbidden_gh.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('invoked')\n",
            encoding="utf-8",
        )
        forbidden_gh.chmod(0o700)

        outcome = DELIVERY.preflight(self.workflow, self.repo, str(forbidden_gh))

        self.assertEqual(outcome["status"], "waiting_external")
        self.assertIn("explicit authority", outcome["failure"])
        self.assertFalse(marker.exists())

    def test_preflight_rejects_remote_repository_mismatch_before_gh(self) -> None:
        command(self.repo, "remote", "set-url", "origin", "https://example.invalid/acme/other.git")
        marker = self.root / "mismatch-gh-invoked"
        forbidden_gh = self.root / "mismatch-forbidden-gh"
        forbidden_gh.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('invoked')\n",
            encoding="utf-8",
        )
        forbidden_gh.chmod(0o700)

        outcome = DELIVERY.preflight(self.workflow, self.repo, str(forbidden_gh))

        self.assertEqual(outcome["status"], "waiting_external")
        self.assertIn("different repositories", outcome["failure"])
        self.assertFalse(marker.exists())

    def test_recursive_split_parallel_worktrees_verification_and_ship_lifecycle(self) -> None:
        reviewer = self.workflow / "runtime" / "fake-decomposition-reviewer"
        reviewer.parent.mkdir(parents=True, exist_ok=True)
        reviewer.write_text(
            "#!/usr/bin/env python3\n"
            "import json,re,sys\n"
            "request=json.load(sys.stdin); prompt=request['prompt']\n"
            "def field(name):\n"
            "  m=re.search(name+r\"='([^']+)'\",prompt); return m.group(1)\n"
            "review={'schema_version':1,'workflow_id':field('workflow_id'),'graph_digest':field('graph_digest'),'methods':['Rumsfeld Matrix','Value of Information','Reversibility','Premortem'],'reviewer':{'agent_id':field('reviewer.agent_id'),'model_class':'small','model_id':'fake-small','independent':True,'context_policy':'fresh-artifacts-only'},'challenges':[{'class':'misread-intent','result':'clear','rationale':'Intent is unchanged.'},{'class':'hidden-dependency','result':'clear','rationale':'Output ancestry is closed.'},{'class':'oracle-gap','result':'clear','rationale':'Locked checks are conserved.'}],'findings':[],'status':'passed','reviewed_at':'2026-07-20T00:00:00Z'}\n"
            "json.dump(review,sys.stdout)\n",
            encoding="utf-8",
        )
        reviewer.chmod(0o700)
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["agent_adapter"] = {
            "schema_version": 1,
            "protocol": "graphflow-agent-adapter-v1",
            "id": "delivery-review-test-v1",
            "argv": ["python3", "runtime/fake-decomposition-reviewer"],
            "env_allow": [],
            "resources": [{"path": "runtime/fake-decomposition-reviewer", "digest": "sha256:" + hashlib.sha256(reviewer.read_bytes()).hexdigest()}],
            "sandbox_modes": ["read-only", "workspace-write"],
            "model_map": {"small": "fake-small", "balanced": "fake-balanced", "frontier": "fake-frontier"},
            "requires_authority": [],
        }
        write_json(runtime_path, runtime)
        DECOMPOSITION.memory_state.command_init(self.workflow, self.repo)

        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        for node in graph["nodes"]:
            if node["id"] == "B":
                node["status"] = "active"
                node["retry"]["attempts"] = 1
            elif node["kind"] != "expand" and node["id"] != "P":
                node["status"] = "pending"
        graph["lifecycle"]["status"] = "active"
        graph["verification"] = {"outcome": "pending", "claims": []}
        write_json(graph_path, graph)
        spec_path = self.workflow / "nodes/B/executor.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["acceptance_checks"] = ["CHK-SHIP-NEGATIVE", "CHK-SHIP-BOUNDARY"]
        write_json(spec_path, spec)
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        next(node for node in graph["nodes"] if node["id"] == "B")["executor"]["digest"] = "sha256:" + hashlib.sha256(spec_path.read_bytes()).hexdigest()
        write_json(graph_path, graph)

        def proposal(node_id: str, parent_measure: int, support_key: str, terminal_key: str, support_checks: list[str], terminal_checks: list[str]) -> dict:
            current = json.loads(graph_path.read_text(encoding="utf-8"))
            parent = next(node for node in current["nodes"] if node["id"] == node_id)
            support_output = {"id": f"handoff-{node_id.lower().replace('.', '-')}", "description": "Bounded decomposition handoff.", "artifact": None}
            scope = parent["scope"]
            return {
                "schema_version": 1,
                "contract_change": "structural",
                "reason_class": "complexity",
                "reason": "Split one bounded analysis step from terminal materialization.",
                "measure": {
                    "name": "lifecycle-points",
                    "parent": parent_measure,
                    "children": [{"key": support_key, "value": 1}, {"key": terminal_key, "value": 3 if parent_measure == 5 else 2}],
                },
                "terminal_child": terminal_key,
                "children": [
                    {
                        "key": support_key, "title": "Bounded analysis", "outcome": "Produce an internal handoff.",
                        "operations": ["implementation"], "methods": ["YAGNI", "Contract Testing"], "skills": ["implement"], "depends_on": [],
                        "scope": {"read": list(scope["read"]), "write": [], "artifacts": [], "decisions": [], "forbidden": list(scope["forbidden"])},
                        "consumes": list(parent["consumes"]), "outputs": [support_output], "acceptance": ["The bounded handoff is explicit."],
                        "acceptance_checks": support_checks, "budget_tokens": 300,
                    },
                    {
                        "key": terminal_key, "title": "Terminal materialization", "outcome": "Preserve the parent output contract.",
                        "operations": ["implementation"], "methods": ["Contract Testing", "DRY"], "skills": ["implement"], "depends_on": [support_key],
                        "scope": {"read": list(scope["read"]), "write": list(scope["write"]), "artifacts": list(scope["artifacts"]), "decisions": list(scope["decisions"]), "forbidden": list(scope["forbidden"])},
                        "consumes": [*parent["consumes"], support_output["id"]], "outputs": list(parent["outputs"]), "acceptance": list(parent["acceptance"]),
                        "acceptance_checks": terminal_checks, "budget_tokens": 600 if parent_measure == 3 else 1000,
                    },
                ],
            }

        def result(node_id: str, decomposition: dict) -> dict:
            _, node, node_spec, _ = DECOMPOSITION.load_executor(self.workflow, node_id)
            return {
                "schema_version": 2, "workflow_id": "publish-queue-bulk-retry", "node_id": node_id,
                "attempt": node["retry"]["attempts"], "idempotency_key": node_spec["idempotency_key"], "status": "decompose",
                "summary": "Bounded recursive decomposition.", "outputs": [], "evidence": [], "memory_delta": None,
                "request": None, "decomposition": decomposition, "usage": {"input_tokens": 10, "output_tokens": 20},
            }

        first = proposal("B", 5, "analyze", "materialize", ["CHK-SHIP-NEGATIVE"], ["CHK-SHIP-BOUNDARY"])
        DECOMPOSITION.apply(self.workflow, self.repo, "B", result("B", first))
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        terminal = next(node for node in graph["nodes"] if node["id"] == "B.materialize")
        terminal["status"] = "active"
        terminal["retry"]["attempts"] = 1
        write_json(graph_path, graph)
        second = proposal("B.materialize", 3, "refine", "finish", ["CHK-SHIP-BOUNDARY"], ["CHK-SHIP-BOUNDARY"])
        DECOMPOSITION.apply(self.workflow, self.repo, "B.materialize", result("B.materialize", second))

        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        recursive_terminal = next(node for node in graph["nodes"] if node["id"] == "B.materialize.finish")
        self.assertEqual(recursive_terminal["decomposition_bound"]["value"], 2)
        selected = WORKFLOW_RUNTIME.select_safe_frontier(
            self.workflow, self.repo, graph, [("C", None), ("D", None)], 2,
        )
        self.assertEqual([node_id for node_id, _ in selected], ["C", "D"])
        registry = WORKSPACES.load_registry(self.workflow)
        self.assertNotEqual(registry["entries"]["workspace-c"]["path"], registry["entries"]["workspace-d"]["path"])

        for node in graph["nodes"]:
            if node["kind"] != "expand":
                node["status"] = "complete"
        graph["lifecycle"]["status"] = "complete"
        graph["verification"] = {
            "outcome": "verified",
            "claims": [
                {
                    "id": f"C-{requirement['id']}", "requirement_id": requirement["id"], "statement": requirement["text"],
                    "state": "verified", "confidence": "high",
                    "evidence": [{"check": "Ship release gate", "artifact": "evidence/attestations/CHK-SHIP-NEGATIVE.json"}],
                    "limitations": [],
                }
                for requirement in graph["objective"]["requirements"]
            ],
        }
        write_json(graph_path, graph)
        verifier_path = Path(WORKSPACES.load_registry(self.workflow)["entries"]["workspace-f"]["path"])
        for check_id in ("CHK-SHIP-NEGATIVE", "CHK-SHIP-BOUNDARY"):
            EVIDENCE.command_run(self.workflow, verifier_path, check_id)
        plan = json.loads((self.workflow / "integrity/verification-plan.json").read_text(encoding="utf-8"))
        review_input = self.root / "recursive-review-input.json"
        write_json(review_input, {
            "schema_version": 1, "verifier_node": "F", "producer_nodes": plan["separation_of_duties"]["producer_nodes"],
            "outcome": "pass", "challenge_classes": ["negative", "boundary"],
            "evidence_attestations": ["evidence/attestations/CHK-SHIP-NEGATIVE.json", "evidence/attestations/CHK-SHIP-BOUNDARY.json"],
            "limitations": [],
        })
        EVIDENCE.command_record_review(self.workflow, verifier_path, review_input)
        EVIDENCE.command_validate(self.workflow, verifier_path, "complete")

        prepared = DELIVERY.prepare(self.workflow, self.repo)
        self.assertEqual(prepared["status"], "waiting_approval")
        self.confirm()
        published = DELIVERY.advance(self.workflow, self.repo, str(self.fake_gh))
        self.assertEqual(published["status"], "published")
        self.assertTrue((self.workflow / "runtime/delivery/proof.json").is_file())

    def test_consumed_request_recovers_after_proof_write_crash_window(self) -> None:
        DELIVERY.prepare(self.workflow, self.repo)
        self.confirm()
        approved_grant = self.delivery()["grant"]
        first = DELIVERY.advance(self.workflow, self.repo, str(self.fake_gh))
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["delivery"].update(status="publishing", grant=approved_grant)
        write_json(runtime_path, runtime)

        recovered = DELIVERY.advance(self.workflow, self.repo, str(self.fake_gh))
        self.assertEqual(recovered["status"], "published")
        self.assertEqual(recovered["release_sha"], first["release_sha"])
        self.assertIsNone(self.delivery()["grant"])

    def test_remote_base_drift_stops_before_push_or_pr(self) -> None:
        DELIVERY.prepare(self.workflow, self.repo)
        self.confirm()
        (self.repo / "base-drift.txt").write_text("drift\n", encoding="utf-8")
        command(self.repo, "add", "base-drift.txt")
        command(self.repo, "commit", "-qm", "chore: advance base")
        command(self.repo, "push", "-q", "origin", "master")
        outcome = DELIVERY.advance(self.workflow, self.repo, str(self.fake_gh))
        self.assertEqual(outcome["status"], "waiting_external")
        self.assertIn("Remote base moved", outcome["failure"])
        self.assertIsNone(self.remote_ref("graphflow/delivery-eval"))
        self.assertFalse((self.workflow / "runtime/delivery/proof.json").exists())

    def test_existing_different_remote_head_never_force_pushes(self) -> None:
        DELIVERY.prepare(self.workflow, self.repo)
        self.confirm()
        base = command(self.repo, "rev-parse", "master")
        command(self.repo, "push", "-q", "origin", f"{base}:refs/heads/graphflow/delivery-eval")
        outcome = DELIVERY.advance(self.workflow, self.repo, str(self.fake_gh))
        self.assertEqual(outcome["status"], "waiting_external")
        self.assertIn("force push is forbidden", outcome["failure"])
        self.assertEqual(self.remote_ref("graphflow/delivery-eval"), base)

    def test_confirmation_digest_covers_ship_manifest(self) -> None:
        prepared = DELIVERY.prepare(self.workflow, self.repo)
        delivery = self.delivery()
        request_path = self.workflow / "runtime/requests" / f"{delivery['request_id']}.json"
        request = json.loads(request_path.read_text(encoding="utf-8"))
        manifest = json.loads((self.workflow / "runtime/delivery/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(request["triage"]["delivery_manifest_digest"], DELIVERY.json_digest(manifest))
        self.assertEqual(request["triage"]["commit_subject"], manifest["commit"]["subject"])
        self.assertEqual(request["triage"]["commit_body"], manifest["commit"]["body"])
        self.assertEqual(request["triage"]["pull_request_title"], manifest["pull_request"]["title"])
        self.assertEqual(request["triage"]["pull_request_body"], manifest["pull_request"]["body"])
        request["triage"]["delivery_manifest_digest"] = "sha256:" + "0" * 64
        write_json(request_path, request)
        rejected = subprocess.run(
            [
                sys.executable, str(CONFIRM), str(self.workflow), "--request-id", request["request_id"],
                "--digest", request["digest"], "--decision", "approved", "--answer", "tampered",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("decision surface", rejected.stderr)
        self.assertEqual(prepared["manifest_digest"], DELIVERY.json_digest(manifest))

    def test_verification_drift_requires_a_fresh_manifest_and_approval(self) -> None:
        first = DELIVERY.prepare(self.workflow, self.repo)
        self.confirm()
        evidence = self.workflow / "evidence/attestations/CHK-SHIP-NEGATIVE.json"
        current = json.loads(evidence.read_text(encoding="utf-8"))
        current["duration_ms"] += 1
        write_json(evidence, current)

        outcome = DELIVERY.advance(self.workflow, self.repo, str(self.fake_gh))
        self.assertEqual(outcome["status"], "waiting_approval")
        self.assertNotEqual(outcome["request_id"], first["request_id"])
        old_request = json.loads((self.workflow / "runtime/requests" / f"{first['request_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(old_request["status"], "superseded")
        self.assertIsNone(self.remote_ref("graphflow/delivery-eval"))

    def test_ship_adapter_accepts_a_repository_configured_remote_and_base(self) -> None:
        command(self.repo, "remote", "rename", "origin", "upstream")
        command(self.repo, "push", "-q", "upstream", "master:main")
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["delivery"]["base_branch"] = "main"
        runtime["delivery"]["remote"] = "upstream"
        write_json(runtime_path, runtime)
        prepared = DELIVERY.prepare(self.workflow, self.repo)
        self.assertEqual(prepared["status"], "waiting_approval")
        self.confirm()
        published = DELIVERY.advance(self.workflow, self.repo, str(self.fake_gh))
        self.assertEqual(published["status"], "published")
        self.assertEqual(self.remote_ref("graphflow/delivery-eval", "upstream"), published["release_sha"])

    def test_fabricated_attestation_blocks_ship_prepare(self) -> None:
        evidence = self.workflow / "evidence/attestations/CHK-SHIP-NEGATIVE.json"
        current = json.loads(evidence.read_text(encoding="utf-8"))
        current["stdout"]["digest"] = "sha256:" + "0" * 64
        write_json(evidence, current)
        with self.assertRaisesRegex(ValueError, "log missing or digest mismatch"):
            DELIVERY.prepare(self.workflow, self.repo)
        self.assertIsNone(self.remote_ref("graphflow/delivery-eval"))


if __name__ == "__main__":
    unittest.main()
