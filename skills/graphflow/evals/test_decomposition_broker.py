#!/usr/bin/env python3
"""Adversarial tests for coordinator-owned runtime decomposition."""

from __future__ import annotations

import importlib.util
import json
import signal
import shutil
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("graphflow_decomposition", ROOT / "scripts" / "decomposition_broker.py")
assert SPEC and SPEC.loader
BROKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BROKER)
import run_workflow as RUNTIME
from skills.graphflow.evals.fixture_support import approve_template_for_execution


class DecompositionBrokerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Graphflow Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "graphflow-test@local.invalid"], check=True)
        (self.repo / ".gitignore").write_text(".graphflow/\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "baseline"], check=True)
        self.workflow = self.repo / ".graphflow" / "workflow"
        shutil.copytree(ROOT / "assets" / "workflow-template", self.workflow)
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        node = next(item for item in graph["nodes"] if item["id"] == "B")
        node["status"] = "active"
        node["retry"]["attempts"] = 1
        node["runtime"]["completed_at"] = None
        node["runtime"]["heartbeat_at"] = "2026-07-20T00:00:00Z"
        for item in graph["nodes"]:
            if item["id"] in {"C", "D", "E", "F"}:
                item["status"] = "pending"
                item["retry"]["attempts"] = 0
        graph["lifecycle"]["status"] = "active"
        graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
        approve_template_for_execution(self.workflow, self.repo)
        BROKER.memory_state.command_init(self.workflow, self.repo)
        self.fake_reviewer = self.workflow / "runtime" / "fake-reviewer.py"
        self.fake_reviewer.parent.mkdir(parents=True, exist_ok=True)
        self.fake_reviewer.write_text(
            "#!/usr/bin/env python3\n"
            "import json,re,sys\n"
            "request=json.load(sys.stdin); prompt=request['prompt']\n"
            "assert request['kind']=='review' and request['sandbox']=='read-only'\n"
            "def field(name):\n"
            "  m=re.search(name+r\"='([^']+)'\",prompt); return m.group(1)\n"
            "review={'schema_version':1,'workflow_id':field('workflow_id'),'graph_digest':field('graph_digest'),'methods':['Rumsfeld Matrix','Value of Information','Reversibility','Premortem'],'reviewer':{'agent_id':field('reviewer.agent_id'),'model_class':'small','model_id':'fake-small','independent':True,'context_policy':'fresh-artifacts-only'},'challenges':[{'class':'misread-intent','result':'clear','rationale':'Objective and acceptance are unchanged.'},{'class':'hidden-dependency','result':'clear','rationale':'Every support child is ancestral to the terminal child.'},{'class':'oracle-gap','result':'clear','rationale':'Existing locked checks are preserved.'}],'findings':[],'status':'passed','reviewed_at':'2026-07-20T00:00:00Z'}\n"
            "json.dump(review,sys.stdout)\n",
            encoding="utf-8",
        )
        self.fake_reviewer.chmod(0o700)
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["agent_adapter"] = {
            "schema_version": 1,
            "protocol": "graphflow-agent-adapter-v1",
            "id": "alternate-review-test-v1",
            "argv": ["python3", "runtime/fake-reviewer.py"],
            "env_allow": [],
            "resources": [{"path": "runtime/fake-reviewer.py", "digest": BROKER.sha256(self.fake_reviewer)}],
            "sandbox_modes": ["read-only", "workspace-write"],
            "model_map": {"small": "fake-small", "balanced": "fake-balanced", "frontier": "fake-frontier"},
            "requires_authority": [],
        }
        runtime_path.write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
        self.open_reviewer = self.workflow / "runtime" / "fake-open-reviewer.py"
        self.open_reviewer.write_text(
            "#!/usr/bin/env python3\n"
            "import json,re,sys\n"
            "request=json.load(sys.stdin); prompt=request['prompt']\n"
            "def field(name):\n"
            "  m=re.search(name+r\"='([^']+)'\",prompt); return m.group(1)\n"
            "finding={'id':'intent-1','question':'Should terminal acceptance preserve the current retry semantics or adopt the newly implied partial-success semantics?','impacts':['acceptance'],'disposition':'pivotal_open','rationale':'The proposal text permits two incompatible acceptance meanings.','evidence':[]}\n"
            "review={'schema_version':1,'workflow_id':field('workflow_id'),'graph_digest':field('graph_digest'),'methods':['Rumsfeld Matrix','Value of Information','Reversibility','Premortem'],'reviewer':{'agent_id':field('reviewer.agent_id'),'model_class':'small','model_id':'fake-small','independent':True,'context_policy':'fresh-artifacts-only'},'challenges':[{'class':'misread-intent','result':'finding','rationale':'Acceptance meaning is ambiguous.'},{'class':'hidden-dependency','result':'clear','rationale':'Dependency ancestry is closed.'},{'class':'oracle-gap','result':'clear','rationale':'Locked check IDs are preserved.'}],'findings':[finding],'status':'open','reviewed_at':'2026-07-20T00:00:00Z'}\n"
            "json.dump(review,sys.stdout)\n",
            encoding="utf-8",
        )
        self.open_reviewer.chmod(0o700)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def select_reviewer(self, path: Path, adapter_id: str) -> None:
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["agent_adapter"].update(
            id=adapter_id,
            argv=["python3", f"runtime/{path.name}"],
            resources=[{"path": f"runtime/{path.name}", "digest": BROKER.sha256(path)}],
        )
        runtime_path.write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")

    def proposal(self) -> dict[str, object]:
        original_output = {
            "id": "bulk-retry-contract",
            "description": "Validated request and response contract.",
            "artifact": "packages/contracts/src/publish-retry.ts",
        }
        return {
            "schema_version": 1,
            "contract_change": "structural",
            "reason_class": "complexity",
            "reason": "Separate bounded analysis from contract materialization.",
            "measure": {
                "name": "contract-points",
                "parent": 5,
                "children": [{"key": "analyze", "value": 2}, {"key": "materialize", "value": 3}],
            },
            "terminal_child": "materialize",
            "children": [
                {
                    "key": "analyze",
                    "title": "Analyze retry invariants",
                    "outcome": "Produce a bounded internal retry-invariant handoff.",
                    "operations": ["implementation"],
                    "methods": ["Contract Testing", "YAGNI"],
                    "skills": ["implement"],
                    "depends_on": [],
                    "scope": {
                        "read": ["docs/CONVENTIONS.md", "packages/contracts/src"],
                        "write": [], "artifacts": [], "decisions": [],
                        "forbidden": ["apps/server", "apps/web"],
                    },
                    "consumes": [],
                    "outputs": [{"id": "retry-invariants", "description": "Internal invariant handoff.", "artifact": None}],
                    "acceptance": ["Retry invariants are explicit."],
                    "acceptance_checks": ["CHK-R1-CONTRACT"],
                    "budget_tokens": 500,
                },
                {
                    "key": "materialize",
                    "title": "Materialize retry contract",
                    "outcome": "Create the unchanged parent contract output.",
                    "operations": ["implementation"],
                    "methods": ["Contract Testing", "DRY"],
                    "skills": ["implement"],
                    "depends_on": ["analyze"],
                    "scope": {
                        "read": ["docs/CONVENTIONS.md", "packages/contracts/src", "packages/contracts/src/publish-retry.ts"],
                        "write": ["packages/contracts/src/publish-retry.ts"],
                        "artifacts": [], "decisions": ["contract.publish.bulk-retry"],
                        "forbidden": ["apps/server", "apps/web"],
                    },
                    "consumes": ["retry-invariants"],
                    "outputs": [original_output],
                    "acceptance": ["Contract tests pass.", "Batch and idempotency rules are explicit."],
                    "acceptance_checks": ["CHK-R1-CONTRACT"],
                    "budget_tokens": 900,
                },
            ],
        }

    def result(self, proposal: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": 2,
            "workflow_id": "publish-queue-bulk-retry",
            "node_id": "B",
            "attempt": 1,
            "idempotency_key": "contract-publish-bulk-retry-v1",
            "status": "decompose",
            "summary": "The unchanged contract has two independently bounded sub-outcomes.",
            "outputs": [], "evidence": [], "memory_delta": None, "request": None,
            "decomposition": proposal,
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }

    def contract(self) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        graph, node, spec, _ = BROKER.load_executor(self.workflow, "B")
        plan = json.loads((self.workflow / "integrity" / "verification-plan.json").read_text(encoding="utf-8"))
        return graph, node, spec, plan

    def test_applies_reviewed_structural_revision_and_preserves_contract(self) -> None:
        before = json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))
        result_path = self.workflow / "runtime" / "results" / "B.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(self.result(self.proposal()), indent=2) + "\n", encoding="utf-8")
        outcome = RUNTIME.consume_result(
            self.workflow, self.repo, self.workflow / "graph.json", "B",
        )
        after = json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))
        parent = next(node for node in after["nodes"] if node["id"] == "B")
        terminal = next(node for node in after["nodes"] if node["id"] == "B.materialize")
        self.assertEqual(outcome, "applied")
        self.assertEqual(parent["kind"], "expand")
        self.assertEqual(parent["status"], "expanded")
        self.assertEqual(terminal["covers"], ["R1"])
        self.assertEqual(terminal["outputs"], next(node for node in before["nodes"] if node["id"] == "B")["outputs"])
        self.assertEqual(after["objective"], before["objective"])
        self.assertEqual(after["objective"]["out_of_scope"], before["objective"]["out_of_scope"])
        self.assertEqual(after["integrity"]["status"], "locked")
        runtime = json.loads((self.workflow / "runtime.json").read_text(encoding="utf-8"))
        self.assertEqual(runtime["decomposition"]["status"], "applied")
        self.assertTrue((self.workflow / runtime["decomposition"]["last_proof"]).is_file())

    def test_scope_expansion_is_rejected(self) -> None:
        proposal = self.proposal()
        proposal["children"][0]["scope"]["read"].append("apps/server")
        graph, node, spec, plan = self.contract()
        with self.assertRaisesRegex(ValueError, "expands parent read scope"):
            BROKER.validate_proposal(graph, node, spec, proposal, plan)

    def test_terminal_acceptance_drift_is_rejected(self) -> None:
        proposal = self.proposal()
        proposal["children"][1]["acceptance"] = ["A weaker success statement."]
        graph, node, spec, plan = self.contract()
        with self.assertRaisesRegex(ValueError, "acceptance text exactly"):
            BROKER.validate_proposal(graph, node, spec, proposal, plan)

    def test_budget_laundering_is_rejected(self) -> None:
        proposal = self.proposal()
        proposal["children"][1]["budget_tokens"] = 1000
        graph, node, spec, plan = self.contract()
        with self.assertRaisesRegex(ValueError, "budgets"):
            BROKER.validate_proposal(graph, node, spec, proposal, plan)

    def test_non_decreasing_complexity_is_rejected(self) -> None:
        proposal = self.proposal()
        proposal["measure"]["children"][1]["value"] = 5
        graph, node, spec, plan = self.contract()
        with self.assertRaisesRegex(ValueError, "strictly below"):
            BROKER.validate_proposal(graph, node, spec, proposal, plan)

    def test_recursive_split_must_continue_inherited_ranking_bound(self) -> None:
        outcome = BROKER.apply(self.workflow, self.repo, "B", self.result(self.proposal()))
        graph, node, spec, _ = BROKER.load_executor(self.workflow, "B.materialize")
        self.assertEqual(node["decomposition_bound"]["policy"], "ranking-function-v1")
        self.assertEqual(node["decomposition_bound"]["name"], "contract-points")
        self.assertEqual(node["decomposition_bound"]["value"], 3)
        plan = json.loads((self.workflow / "integrity" / "verification-plan.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "inherited bound"):
            BROKER.validate_proposal(graph, node, spec, self.proposal(), plan)
        self.assertEqual(outcome["status"], "applied")

    def test_decompose_envelope_cannot_smuggle_other_result_channels(self) -> None:
        result = self.result(self.proposal())
        result["memory_delta"] = {"unexpected": True}
        errors = RUNTIME.validate_result(
            result, "publish-queue-bulk-retry", "B", 1, "contract-publish-bulk-retry-v1",
        )
        self.assertIn("decompose result must leave memory_delta and request null", errors)

    def test_committed_journal_rolls_forward_runtime_after_crash(self) -> None:
        outcome = BROKER.apply(self.workflow, self.repo, "B", self.result(self.proposal()))
        journal_path = self.workflow / "runtime" / "decompositions" / outcome["revision_id"] / "journal.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["status"] = "committed"
        journal_path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["decomposition"].update(status="reviewing", revision=0, last_proof=None, failure=None)
        runtime_path.write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
        recovered = BROKER.recover_pending(self.workflow, self.repo)
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual(recovered, [{"revision_id": outcome["revision_id"], "action": "finalized"}])
        self.assertEqual(journal["status"], "finalized")
        self.assertEqual(runtime["decomposition"]["status"], "applied")
        self.assertEqual(runtime["decomposition"]["revision"], 1)

    def test_committed_recovery_validation_failure_rolls_back_once(self) -> None:
        before = json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))
        result_path = self.workflow / "runtime/results/B.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(self.result(self.proposal())), encoding="utf-8")
        outcome = BROKER.apply(self.workflow, self.repo, "B", self.result(self.proposal()))
        record = self.workflow / "runtime/decompositions" / outcome["revision_id"]
        journal_path = record / "journal.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["status"] = "committed"
        journal_path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["decomposition"].update(status="reviewing", revision=0, last_proof=None, failure=None)
        runtime_path.write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
        original_validate = BROKER.validate_candidate
        try:
            BROKER.validate_candidate = lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("injected committed validation failure"))
            recovered = BROKER.recover_pending(self.workflow, self.repo)
        finally:
            BROKER.validate_candidate = original_validate
        graph = json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        self.assertEqual(recovered, [{"revision_id": outcome["revision_id"], "action": "rolled_back"}])
        self.assertEqual(BROKER.canonical_graph_digest(graph), BROKER.canonical_graph_digest(before))
        self.assertEqual(journal["status"], "rolled_back")
        self.assertEqual(runtime["decomposition"]["status"], "blocked")
        self.assertEqual(BROKER.recover_pending(self.workflow, self.repo), [])

    def test_finalized_journal_is_historical_not_replayed(self) -> None:
        BROKER.apply(self.workflow, self.repo, "B", self.result(self.proposal()))
        first = BROKER.recover_pending(self.workflow, self.repo)
        second = BROKER.recover_pending(self.workflow, self.repo)
        runtime = json.loads((self.workflow / "runtime.json").read_text(encoding="utf-8"))
        self.assertEqual(first, [])
        self.assertEqual(second, [])
        self.assertEqual(runtime["decomposition"]["revision"], 1)

    def test_interrupted_commit_rolls_back_from_write_ahead_journal(self) -> None:
        before = json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))
        result_path = self.workflow / "runtime" / "results" / "B.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(self.result(self.proposal()), indent=2) + "\n", encoding="utf-8")
        outcome = BROKER.apply(self.workflow, self.repo, "B", self.result(self.proposal()))
        record = self.workflow / "runtime" / "decompositions" / outcome["revision_id"]
        journal_path = record / "journal.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["status"] = "committing"
        journal_path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["decomposition"].update(status="reviewing", revision=0, last_proof=None, failure=None)
        runtime_path.write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")

        recovered = BROKER.recover_pending(self.workflow, self.repo)
        after = json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual(recovered, [{"revision_id": outcome["revision_id"], "action": "rolled_back"}])
        self.assertEqual(BROKER.canonical_graph_digest(after), BROKER.canonical_graph_digest(before))
        self.assertEqual(journal["status"], "rolled_back")
        self.assertEqual(runtime["decomposition"]["status"], "blocked")
        self.assertFalse((self.workflow / "nodes" / "B.analyze").exists())
        self.assertFalse((self.workflow / "nodes" / "B.materialize").exists())
        self.assertFalse(result_path.exists())
        self.assertTrue((record / "aborted-result.json").is_file())

    def test_recovery_rejects_untrusted_journal_paths_before_deletion(self) -> None:
        outcome = BROKER.apply(self.workflow, self.repo, "B", self.result(self.proposal()))
        record = self.workflow / "runtime" / "decompositions" / outcome["revision_id"]
        journal_path = record / "journal.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["status"] = "committing"
        journal["children"] = ["../../preserve"]
        journal_path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
        preserve = self.repo / "preserve"
        preserve.mkdir()
        (preserve / "sentinel").write_text("keep\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "journal children"):
            BROKER.recover_pending(self.workflow, self.repo)
        self.assertTrue((preserve / "sentinel").is_file())

    def test_semantic_decomposition_is_rejected(self) -> None:
        proposal = self.proposal()
        proposal["contract_change"] = "semantic"
        graph, node, spec, plan = self.contract()
        with self.assertRaisesRegex(ValueError, "structural"):
            BROKER.validate_proposal(graph, node, spec, proposal, plan)

    def test_failed_review_does_not_modify_graph(self) -> None:
        before = (self.workflow / "graph.json").read_bytes()
        bad_review = self.workflow / "runtime" / "bad-review.json"
        bad_review.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "review rejected"):
            BROKER.apply(self.workflow, self.repo, "B", self.result(self.proposal()), bad_review)
        self.assertEqual((self.workflow / "graph.json").read_bytes(), before)
        runtime = json.loads((self.workflow / "runtime.json").read_text(encoding="utf-8"))
        self.assertEqual(runtime["decomposition"]["status"], "blocked")

    def test_pivotal_review_becomes_one_digest_bound_branch_rebase_request(self) -> None:
        before = (self.workflow / "graph.json").read_bytes()
        result_path = self.workflow / "runtime" / "results" / "B.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(self.result(self.proposal()), indent=2) + "\n", encoding="utf-8")

        self.select_reviewer(self.open_reviewer, "open-review-test-v1")
        try:
            outcome = RUNTIME.consume_result(
                self.workflow, self.repo, self.workflow / "graph.json", "B",
            )
        finally:
            self.select_reviewer(self.fake_reviewer, "alternate-review-test-v1")

        graph = json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))
        node = next(item for item in graph["nodes"] if item["id"] == "B")
        requests = list((self.workflow / "runtime" / "requests").glob("decomposition-rebase-*.json"))
        runtime = json.loads((self.workflow / "runtime.json").read_text(encoding="utf-8"))
        self.assertEqual(outcome, "waiting_rebase")
        self.assertEqual(node["status"], "waiting_user")
        self.assertEqual(len(requests), 1)
        request = json.loads(requests[0].read_text(encoding="utf-8"))
        self.assertEqual(request["triage"]["blocking_scope"], "branch")
        self.assertEqual(request["triage"]["resolution_mode"], "rebase")
        self.assertEqual(request["triage"]["request_graph_digest"], BROKER.canonical_graph_digest(json.loads(before)))
        self.assertEqual(request["triage"]["affected_nodes"], ["B", "C", "D", "E", "F"])
        self.assertEqual(runtime["decomposition"]["status"], "waiting_rebase")
        self.assertFalse((self.workflow / "nodes" / "B.analyze").exists())
        decisions = list((self.workflow / "runtime/decompositions/rejected").glob("*.json"))
        self.assertEqual(len(decisions), 1)
        decision = json.loads(decisions[0].read_text(encoding="utf-8"))
        self.assertEqual(decision["request_id"], request["request_id"])
        self.assertEqual(decision["request_digest"], request["digest"])
        self.assertTrue((self.workflow / decision["review_cache"]).is_file())

    def test_content_addressed_review_cache_survives_retry_without_model_call(self) -> None:
        config = BROKER.default_config()
        proposal = self.proposal()
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = Path(first_dir) / "workflow"
            second = Path(second_dir) / "workflow"
            shutil.copytree(self.workflow, first)
            BROKER.build_candidate(first, "B", proposal)
            review, cache_key, cache_hit = BROKER.obtain_review(
                self.workflow, first, proposal, config, "review-first", None,
            )
            self.assertFalse(cache_hit)
            self.assertEqual(review["status"], "passed")
            self.assertTrue((self.workflow / "runtime" / "decompositions" / "cache" / f"{cache_key}.json").is_file())

            shutil.copytree(self.workflow, second)
            BROKER.build_candidate(second, "B", proposal)
            cached, repeated_key, repeated_hit = BROKER.obtain_review(
                self.workflow, second, proposal, config, "review-retry", None,
            )
            self.assertTrue(repeated_hit)
            self.assertEqual(repeated_key, cache_key)
            self.assertEqual(cached, review)

    def test_review_cache_is_invalidated_by_plan_or_prompt_contract_change(self) -> None:
        config = BROKER.default_config()
        proposal = self.proposal()
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "workflow"
            shutil.copytree(self.workflow, candidate)
            BROKER.build_candidate(candidate, "B", proposal)
            graph = json.loads((candidate / "graph.json").read_text(encoding="utf-8"))
            plan = json.loads((candidate / "integrity/verification-plan.json").read_text(encoding="utf-8"))
            original_key, identity = BROKER.review_cache_key(graph, proposal, plan, config)
            changed_plan = deepcopy(plan)
            changed_plan["checks"][0]["timeout_seconds"] += 1
            plan_key, plan_identity = BROKER.review_cache_key(graph, proposal, changed_plan, config)
            original_policy = BROKER.REVIEW_PROMPT_POLICY
            try:
                BROKER.REVIEW_PROMPT_POLICY = original_policy + " Fresh policy revision."
                prompt_key, prompt_identity = BROKER.review_cache_key(graph, proposal, plan, config)
            finally:
                BROKER.REVIEW_PROMPT_POLICY = original_policy
            self.assertNotEqual(plan_key, original_key)
            self.assertNotEqual(prompt_key, original_key)
            self.assertNotEqual(plan_identity["verification_plan_digest"], identity["verification_plan_digest"])
            self.assertNotEqual(prompt_identity["review_contract_digest"], identity["review_contract_digest"])

    def test_corrupt_merkle_backup_blocks_recovery_before_live_mutation(self) -> None:
        outcome = BROKER.apply(self.workflow, self.repo, "B", self.result(self.proposal()))
        record = self.workflow / "runtime" / "decompositions" / outcome["revision_id"]
        journal_path = record / "journal.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["status"] = "committing"
        journal_path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
        (record / "backup" / "graph.json").write_text("{}\n", encoding="utf-8")
        live_digest = BROKER.canonical_graph_digest(json.loads((self.workflow / "graph.json").read_text(encoding="utf-8")))

        with self.assertRaisesRegex(ValueError, "backup leaf|manifest"):
            BROKER.recover_pending(self.workflow, self.repo)

        self.assertEqual(
            BROKER.canonical_graph_digest(json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))),
            live_digest,
        )
        self.assertTrue((self.workflow / "nodes" / "B.analyze").is_dir())

    def test_sigkill_at_write_boundaries_recovers_with_rollback_or_rollforward(self) -> None:
        worker = (
            "import importlib.util,json,os,signal,sys; from pathlib import Path; "
            "spec=importlib.util.spec_from_file_location('broker',sys.argv[1]); broker=importlib.util.module_from_spec(spec); spec.loader.exec_module(broker); "
            "point=sys.argv[5]; hook=lambda name: os.kill(os.getpid(),signal.SIGKILL) if name==point else None; "
            "broker.apply(Path(sys.argv[2]),Path(sys.argv[3]),'B',json.loads(Path(sys.argv[4]).read_text()),fault_hook=hook)"
        )
        proposal = self.proposal()
        result = self.result(proposal)
        revision_id = f"b-a1-{BROKER.json_digest(proposal).split(':', 1)[1][:12]}"
        for point in ("prepared", "child-copied", "validated", "committed"):
            with self.subTest(point=point):
                case = Path(self.temporary.name) / f"workflow-{point}"
                shutil.copytree(self.workflow, case)
                result_path = case / "runtime" / "results" / "B.json"
                result_path.parent.mkdir(parents=True, exist_ok=True)
                result_path.write_text(json.dumps(result), encoding="utf-8")
                old_digest = BROKER.canonical_graph_digest(json.loads((case / "graph.json").read_text(encoding="utf-8")))
                completed = subprocess.run(
                    [sys.executable, "-c", worker, str(ROOT / "scripts" / "decomposition_broker.py"), str(case), str(self.repo), str(result_path), point],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(completed.returncode, -signal.SIGKILL, completed.stdout + completed.stderr)
                recovered = BROKER.recover_pending(case, self.repo)
                journal = json.loads((case / "runtime" / "decompositions" / revision_id / "journal.json").read_text(encoding="utf-8"))
                graph = json.loads((case / "graph.json").read_text(encoding="utf-8"))
                if point == "committed":
                    self.assertEqual(recovered[0]["action"], "finalized")
                    self.assertEqual(journal["status"], "finalized")
                    self.assertTrue((case / "nodes" / "B.analyze").is_dir())
                else:
                    self.assertEqual(recovered[0]["action"], "rolled_back")
                    self.assertEqual(journal["status"], "rolled_back")
                    self.assertEqual(BROKER.canonical_graph_digest(graph), old_digest)
                    self.assertFalse((case / "nodes" / "B.analyze").exists())


if __name__ == "__main__":
    unittest.main()
