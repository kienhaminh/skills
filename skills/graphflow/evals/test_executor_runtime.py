#!/usr/bin/env python3
"""Regression tests for caller-independent executor dispatch and confirmations."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_workflow as WORKFLOW_RUNTIME
import agent_adapter
import memory_state
from executor_common import canonical_graph_digest, question_surface_digest
from skills.graphflow.evals.fixture_support import approve_manifest, complete_clear_review


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "workflow-template"
NODE_RUNNER = ROOT / "scripts" / "node_runner.py"
WORKFLOW_RUNNER = ROOT / "scripts" / "run_workflow.py"
CONFIRM = ROOT / "scripts" / "confirm_workflow.py"
EVIDENCE = ROOT / "scripts" / "evidence_runner.py"
QUESTION_GATE = ROOT / "scripts" / "question_gate.py"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class ExecutorRuntimeTests(unittest.TestCase):
    def lock_question_review(self) -> None:
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["question_gate"]["review"] = {
            "status": "required",
            "artifact": "question-review.json",
            "digest": None,
            "graph_digest": None,
            "reviewer_id": None,
        }
        write_json(graph_path, graph)
        review_path = self.workflow / "question-review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        complete_clear_review(review)
        review["workflow_id"] = graph["workflow_id"]
        review["graph_digest"] = question_surface_digest(graph)
        review["reviewer"]["agent_id"] = "independent-runtime-test-reviewer"
        review["reviewed_at"] = "2026-07-19T00:00:00Z"
        write_json(review_path, review)
        locked = subprocess.run(
            [sys.executable, str(QUESTION_GATE), "lock", str(self.workflow)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(locked.returncode, 0, locked.stdout + locked.stderr)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self.workflow = self.repo / ".graphflow" / "workflows" / "executor-runtime-eval"
        shutil.copytree(TEMPLATE, self.workflow)
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Graphflow Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "graphflow-test@local.invalid"], check=True)
        (self.repo / ".gitignore").write_text(".graphflow/\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "baseline"], check=True)
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["workflow_id"] = "executor-runtime-eval"
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["workflow_id"] = graph["workflow_id"]
        adapter_path = self.workflow / "adapters" / "fake-tool.py"
        adapter_path.parent.mkdir(parents=True, exist_ok=True)
        adapter_path.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "request=json.load(sys.stdin)\n"
            "assert request['protocol']=='graphflow-agent-adapter-v1'\n"
            "if request['prompt'].startswith('Inspect the approved prototype'):\n"
            "  assert 'Bounded shared-memory capsule' in request['prompt']\n"
            "result={'schema_version':2,'workflow_id':'executor-runtime-eval','node_id':'P','attempt':1,'idempotency_key':'fake-agent-adapter-v1','status':'succeeded','summary':'Fresh read-only inspection completed.','outputs':[],'evidence':[],'memory_delta':None,'request':None,'decomposition':None,'usage':{'input_tokens':5,'output_tokens':7}}\n"
            "json.dump(result,sys.stdout)\n",
            encoding="utf-8",
        )
        runtime["agent_adapter"] = {
            "schema_version": 1,
            "protocol": "graphflow-agent-adapter-v1",
            "id": "fake-tool-v1",
            "argv": ["python3", "adapters/fake-tool.py"],
            "env_allow": [],
            "resources": [{"path": "adapters/fake-tool.py", "digest": digest(adapter_path)}],
            "sandbox_modes": ["read-only", "workspace-write"],
            "model_map": {"small": "fake-small", "balanced": "fake-balanced", "frontier": "fake-frontier"},
            "requires_authority": [],
        }
        write_json(runtime_path, runtime)
        workspaces_path = self.workflow / "runtime" / "workspaces.json"
        workspaces = json.loads(workspaces_path.read_text(encoding="utf-8"))
        workspaces["workflow_id"] = graph["workflow_id"]
        write_json(workspaces_path, workspaces)
        plan_path = self.workflow / "integrity" / "verification-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["workflow_id"] = graph["workflow_id"]
        manifest_path = self.workflow / "prototype" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["workflow_id"] = graph["workflow_id"]
        write_json(manifest_path, manifest)
        approve_manifest(self.workflow, graph)
        node_p = next(node for node in graph["nodes"] if node["id"] == "P")
        node_p["status"] = "complete"
        node_p["retry"]["attempts"] = 1
        next(node for node in graph["nodes"] if node["id"] == "B")["status"] = "complete"

        relative_manifest = ".graphflow/workflows/executor-runtime-eval/prototype/manifest.json"
        plan["checks"][0]["argv"] = ["python3", "-m", "json.tool", relative_manifest]
        plan["checks"][0]["cwd"] = "repo"
        plan["checks"][0]["watch"] = [{"root": "repo", "path": relative_manifest}]
        write_json(plan_path, plan)

        spec_path = self.workflow / "nodes" / "P" / "executor.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["argv"] = ["python3", "-m", "json.tool", relative_manifest]
        write_json(spec_path, spec)
        node_p["executor"]["digest"] = digest(spec_path)
        write_json(graph_path, graph)
        self.lock_question_review()
        locked = subprocess.run(
            [sys.executable, str(EVIDENCE), "lock", str(self.workflow), "--repo-root", str(self.repo)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(locked.returncode, 0, locked.stdout + locked.stderr)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_command_node_runs_and_is_accepted_without_caller(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(NODE_RUNNER), str(self.workflow), "--node", "P", "--repo-root", str(self.repo)],
            capture_output=True, text=True, check=False,
        )
        result_path = self.workflow / "runtime" / "results" / "P.json"
        detail = result_path.read_text(encoding="utf-8") if result_path.is_file() else "result missing"
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr + detail)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "succeeded")
        self.assertTrue(any(item.get("check") == "CHK-R1-CONTRACT" for item in result["evidence"]))

    def test_agent_adapter_uses_structured_noninteractive_result(self) -> None:
        prompt_path = self.workflow / "nodes" / "P" / "prompt.md"
        prompt_path.write_text("Inspect the approved prototype without changing it.\n", encoding="utf-8")
        spec_path = self.workflow / "nodes" / "P" / "executor.json"
        spec = {
            "schema_version": 2,
            "node_id": "P",
            "type": "agent",
            "workspace": {"mode": "primary", "ref": "primary", "subdir": "."},
            "timeout_seconds": 30,
            "idempotency_key": "fake-agent-adapter-v1",
            "result_schema": "nodes/node-result.schema.json",
            "acceptance_checks": ["CHK-R1-CONTRACT"],
            "env_allow": [],
            "requires_authority": [],
            "resources": [
                {"path": "nodes/node-result.schema.json", "digest": digest(self.workflow / "nodes" / "node-result.schema.json")},
                {"path": "nodes/P/prompt.md", "digest": digest(prompt_path)},
            ],
            "prompt": "nodes/P/prompt.md",
            "model_class": "small",
            "reasoning_effort": "low",
            "sandbox": "read-only",
        }
        write_json(spec_path, spec)
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        node_p = next(node for node in graph["nodes"] if node["id"] == "P")
        node_p["executor"].update(type="agent", digest=digest(spec_path))
        graph["integrity"].update(status="proposed", plan_digest=None, runner_digest=None)
        write_json(graph_path, graph)
        write_json(
            self.workflow / "integrity" / "lock.json",
            {"schema_version": 1, "workflow_id": graph["workflow_id"], "status": "template", "plan_digest": None, "runner_digest": None, "contract_digest": None, "locked_at": None},
        )
        relocked = subprocess.run(
            [sys.executable, str(EVIDENCE), "lock", str(self.workflow), "--repo-root", str(self.repo)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(relocked.returncode, 0, relocked.stdout + relocked.stderr)
        memory_state.command_init(self.workflow, self.repo)
        memory_state.command_view(self.workflow, self.repo, "P", 12, 6000, None)
        completed = subprocess.run(
            [sys.executable, str(NODE_RUNNER), str(self.workflow), "--node", "P", "--repo-root", str(self.repo)],
            capture_output=True, text=True, check=False,
        )
        result_path = self.workflow / "runtime" / "results" / "P.json"
        detail = result_path.read_text(encoding="utf-8") if result_path.is_file() else "result missing"
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr + detail)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["usage"]["output_tokens"], 7)

    def test_two_distinct_adapter_wrappers_share_the_same_protocol(self) -> None:
        request = {
            "schema_version": 1,
            "protocol": "graphflow-agent-adapter-v1",
            "kind": "node",
            "prompt": "Return the bounded result.",
            "cwd": str(self.repo),
            "output_schema": str(self.workflow / "nodes/node-result.schema.json"),
            "sandbox": "read-only",
            "model_class": "small",
            "reasoning_effort": "low",
        }
        first, first_meta = agent_adapter.invoke(self.workflow, request, timeout_seconds=30)
        self.assertEqual(first["status"], "succeeded")
        self.assertEqual(first_meta["adapter_id"], "fake-tool-v1")

        alternate = self.workflow / "adapters" / "alternate-tool.py"
        alternate.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "request=json.load(sys.stdin)\n"
            "assert request['model']=='alternate-small'\n"
            "value={'schema_version':2,'workflow_id':'executor-runtime-eval','node_id':'P','attempt':1,'idempotency_key':'fake-agent-adapter-v1','status':'succeeded','summary':'Alternate tool completed.','outputs':[],'evidence':[],'memory_delta':None,'request':None,'decomposition':None,'usage':{'input_tokens':3,'output_tokens':4}}\n"
            "json.dump(value,sys.stdout)\n",
            encoding="utf-8",
        )
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["agent_adapter"].update(
            id="alternate-tool-v1",
            argv=["python3", "adapters/alternate-tool.py"],
            resources=[{"path": "adapters/alternate-tool.py", "digest": digest(alternate)}],
            model_map={"small": "alternate-small"},
        )
        write_json(runtime_path, runtime)
        second, second_meta = agent_adapter.invoke(self.workflow, request, timeout_seconds=30)
        self.assertEqual(second["summary"], "Alternate tool completed.")
        self.assertEqual(second_meta["adapter_id"], "alternate-tool-v1")

    def test_missing_adapter_is_rejected_before_dispatch(self) -> None:
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["agent_adapter"] = None
        write_json(runtime_path, runtime)
        completed = subprocess.run(
            [sys.executable, str(WORKFLOW_RUNNER), str(self.workflow), "--repo-root", str(self.repo), "--dry-run"],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("runtime.agent_adapter must be configured", completed.stderr)
        self.assertFalse((self.workflow / "runtime/events.jsonl").exists())

    def test_adapter_resource_drift_is_rejected_before_dispatch(self) -> None:
        adapter_path = self.workflow / "adapters/fake-tool.py"
        adapter_path.write_text(adapter_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(WORKFLOW_RUNNER), str(self.workflow), "--repo-root", str(self.repo), "--dry-run"],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("agent_adapter resource digest mismatch", completed.stderr)
        self.assertFalse((self.workflow / "runtime/events.jsonl").exists())

    def test_adapter_capability_mismatch_is_rejected_before_dispatch(self) -> None:
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["agent_adapter"]["model_map"] = {"small": "fake-small"}
        write_json(runtime_path, runtime)
        completed = subprocess.run(
            [sys.executable, str(WORKFLOW_RUNNER), str(self.workflow), "--repo-root", str(self.repo), "--dry-run"],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("no model mapping for 'balanced'", completed.stderr)
        self.assertFalse((self.workflow / "runtime/events.jsonl").exists())

    def test_adapter_authority_must_be_declared_by_each_agent_executor(self) -> None:
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["agent_adapter"]["requires_authority"] = ["network"]
        write_json(runtime_path, runtime)
        completed = subprocess.run(
            [sys.executable, str(WORKFLOW_RUNNER), str(self.workflow), "--repo-root", str(self.repo), "--dry-run"],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("must declare adapter authority: network", completed.stderr)
        self.assertFalse((self.workflow / "runtime/events.jsonl").exists())

    def test_digest_drift_is_rejected(self) -> None:
        spec_path = self.workflow / "nodes" / "P" / "executor.json"
        spec_path.write_text(spec_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(NODE_RUNNER), str(self.workflow), "--node", "P", "--repo-root", str(self.repo)],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("digest mismatch", completed.stderr)

    def test_missing_runtime_authority_is_rejected(self) -> None:
        spec_path = self.workflow / "nodes" / "P" / "executor.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["requires_authority"] = ["local_write"]
        write_json(spec_path, spec)
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        next(node for node in graph["nodes"] if node["id"] == "P")["executor"]["digest"] = digest(spec_path)
        write_json(graph_path, graph)
        completed = subprocess.run(
            [sys.executable, str(NODE_RUNNER), str(self.workflow), "--node", "P", "--repo-root", str(self.repo)],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("authority is missing", completed.stderr)

    def test_executor_cannot_self_grant_runtime_authority(self) -> None:
        tamper = self.workflow / "nodes" / "P" / "tamper.py"
        tamper.write_text(
            "import json\n"
            "from pathlib import Path\n"
            "p=Path('.graphflow/workflows/executor-runtime-eval/runtime.json')\n"
            "v=json.loads(p.read_text())\n"
            "v['authority']['local_write']=True\n"
            "p.write_text(json.dumps(v))\n",
            encoding="utf-8",
        )
        spec_path = self.workflow / "nodes" / "P" / "executor.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["argv"] = ["python3", ".graphflow/workflows/executor-runtime-eval/nodes/P/tamper.py"]
        spec["resources"].append({"path": "nodes/P/tamper.py", "digest": digest(tamper)})
        write_json(spec_path, spec)
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        next(node for node in graph["nodes"] if node["id"] == "P")["executor"]["digest"] = digest(spec_path)
        write_json(graph_path, graph)
        completed = subprocess.run(
            [sys.executable, str(NODE_RUNNER), str(self.workflow), "--node", "P", "--repo-root", str(self.repo)],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        result = json.loads((self.workflow / "runtime" / "results" / "P.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "failed")
        self.assertIn("control-plane mutation", result["summary"])
        runtime = json.loads((self.workflow / "runtime.json").read_text(encoding="utf-8"))
        self.assertIs(runtime["authority"]["local_write"], False)

    def test_executor_cannot_create_new_control_plane_files_or_symlinks(self) -> None:
        tamper = self.workflow / "nodes" / "P" / "forge-control-plane.py"
        tamper.write_text(
            "from pathlib import Path\n"
            "root=Path('.graphflow/workflows/executor-runtime-eval')\n"
            "targets=[root/'runtime/decompositions/cache/forged.json',root/'runtime/requests/forged.json',root/'nodes/forged/executor.json']\n"
            "for target in targets:\n"
            " target.parent.mkdir(parents=True,exist_ok=True); target.write_text('{}')\n"
            "(root/'runtime/progress/P.json').write_text('{\"node_id\":\"P\",\"phase\":\"accepted\"}')\n"
            "link=root/'runtime/delivery/forged-link'\n"
            "link.parent.mkdir(parents=True,exist_ok=True); link.symlink_to(root/'runtime.json')\n",
            encoding="utf-8",
        )
        spec_path = self.workflow / "nodes" / "P" / "executor.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["argv"] = ["python3", ".graphflow/workflows/executor-runtime-eval/nodes/P/forge-control-plane.py"]
        spec["resources"].append({"path": "nodes/P/forge-control-plane.py", "digest": digest(tamper)})
        write_json(spec_path, spec)
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        next(node for node in graph["nodes"] if node["id"] == "P")["executor"]["digest"] = digest(spec_path)
        write_json(graph_path, graph)

        completed = subprocess.run(
            [sys.executable, str(NODE_RUNNER), str(self.workflow), "--node", "P", "--repo-root", str(self.repo)],
            capture_output=True, text=True, check=False,
        )

        self.assertNotEqual(completed.returncode, 0)
        result = json.loads((self.workflow / "runtime/results/P.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "failed")
        self.assertIn("control-plane mutation", result["summary"])
        self.assertIn("runtime/progress/P.json", result["summary"])
        for relative in (
            "runtime/decompositions/cache/forged.json", "runtime/requests/forged.json",
            "nodes/forged/executor.json", "runtime/delivery/forged-link",
        ):
            self.assertFalse((self.workflow / relative).exists())
        quarantine = self.workflow / "runtime/quarantine/P/control-plane"
        self.assertTrue((quarantine / "runtime/decompositions/cache/forged.json").is_file())
        self.assertTrue((quarantine / "runtime/requests/forged.json").is_file())
        self.assertTrue((quarantine / "nodes/forged").is_dir())
        self.assertTrue((quarantine / "runtime/delivery/forged-link").is_symlink())

    def test_workflow_dry_run_has_no_caller_dependency(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(WORKFLOW_RUNNER), str(self.workflow), "--repo-root", str(self.repo), "--dry-run"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertIs(result["caller_required"], False)
        self.assertEqual(result["workflow_id"], "executor-runtime-eval")

    def test_runner_brokers_missing_authority_as_node_scoped_grant(self) -> None:
        graph_path = self.workflow / "graph.json"
        created = WORKFLOW_RUNTIME.ensure_authority_requests(self.workflow, graph_path)
        self.assertIn("D", created)
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        self.assertEqual(next(node for node in graph["nodes"] if node["id"] == "D")["status"], "waiting_approval")
        request_path = WORKFLOW_RUNTIME.request_path_for(self.workflow, "D")
        self.assertIsNotNone(request_path)
        request = json.loads(request_path.read_text(encoding="utf-8"))
        self.assertEqual(request["triage"]["authority_capabilities"], ["local_write"])
        confirmed = subprocess.run(
            [sys.executable, str(CONFIRM), str(self.workflow), "--request-id", request["request_id"], "--digest", request["digest"], "--decision", "approved", "--answer", "grant"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(confirmed.returncode, 0, confirmed.stdout + confirmed.stderr)
        runtime = json.loads((self.workflow / "runtime.json").read_text(encoding="utf-8"))
        self.assertEqual(runtime["authority_grants"]["D"]["capabilities"], ["local_write"])
        self.assertEqual(WORKFLOW_RUNTIME.approved_resumes(self.workflow, self.repo, graph_path), [("D", request_path)])

    def test_workflow_runner_dispatches_isolated_command_frontier_without_caller(self) -> None:
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["intent_baseline"] = {
            "required": False,
            "status": "not_required",
            "manifest": None,
            "digest": None,
            "approval": None,
            "not_required_reason": "A machine oracle fully defines this deterministic runner test.",
        }
        graph["nodes"] = [node for node in graph["nodes"] if node["id"] != "P"]
        node_b = next(node for node in graph["nodes"] if node["id"] == "B")
        node_b["status"] = "pending"
        node_b["depends_on"] = []
        node_b["retry"]["attempts"] = 0
        for node in graph["nodes"]:
            if node["id"] == "C":
                node["status"] = "pending"
            if node["id"] in {"E", "F"}:
                node["status"] = "blocked"
        work_script = self.workflow / "nodes" / "B" / "work.py"
        work_script.write_text(
            "from pathlib import Path\n"
            "p=Path('packages/contracts/src/publish-retry.ts')\n"
            "p.parent.mkdir(parents=True, exist_ok=True)\n"
            "p.write_text('export const retry = true;\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )
        spec_path = self.workflow / "nodes" / "B" / "executor.json"
        spec = {
            "schema_version": 2,
            "node_id": "B",
            "type": "command",
            "workspace": {"mode": "worktree", "ref": "workspace-b", "subdir": "."},
            "timeout_seconds": 30,
            "idempotency_key": "command-frontier-v1",
            "result_schema": "nodes/node-result.schema.json",
            "acceptance_checks": ["CHK-R1-CONTRACT"],
            "env_allow": [],
            "requires_authority": ["local_write"],
            "resources": [
                {"path": "nodes/node-result.schema.json", "digest": digest(self.workflow / "nodes" / "node-result.schema.json")},
                {"path": "nodes/B/work.py", "digest": digest(work_script)},
            ],
            "argv": ["python3", "-c", "from pathlib import Path; p=Path('packages/contracts/src/publish-retry.ts'); p.parent.mkdir(parents=True, exist_ok=True); p.write_text('export const retry = true;\\n', encoding='utf-8')"],
        }
        write_json(spec_path, spec)
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["authority"]["local_write"] = True
        write_json(runtime_path, runtime)
        node_b["executor"].update(type="command", digest=digest(spec_path))
        node_b["isolation"] = "worktree"
        graph["integrity"].update(status="proposed", plan_digest=None, runner_digest=None)
        write_json(graph_path, graph)
        plan_path = self.workflow / "integrity" / "verification-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        check = next(item for item in plan["checks"] if item["id"] == "CHK-R1-CONTRACT")
        check["argv"] = [
            "python3",
            "-c",
            "from pathlib import Path; assert Path('packages/contracts/src/publish-retry.ts').read_text(encoding='utf-8') == 'export const retry = true;\\n'",
        ]
        check["cwd"] = "repo"
        check["watch"] = [{"root": "repo", "path": "packages/contracts/src/publish-retry.ts"}]
        write_json(plan_path, plan)
        write_json(
            self.workflow / "integrity" / "lock.json",
            {
                "schema_version": 1,
                "workflow_id": graph["workflow_id"],
                "status": "template",
                "plan_digest": None,
                "runner_digest": None,
                "contract_digest": None,
                "locked_at": None,
            },
        )
        self.lock_question_review()
        relocked = subprocess.run(
            [sys.executable, str(EVIDENCE), "lock", str(self.workflow), "--repo-root", str(self.repo)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(relocked.returncode, 0, relocked.stdout + relocked.stderr)
        completed = subprocess.run(
            [sys.executable, str(WORKFLOW_RUNNER), str(self.workflow), "--repo-root", str(self.repo), "--once"],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)  # Remaining template branches are deliberately blocked.
        updated = json.loads(graph_path.read_text(encoding="utf-8"))
        self.assertEqual(
            next(node for node in updated["nodes"] if node["id"] == "B")["status"],
            "complete",
            completed.stdout + completed.stderr
            + (self.workflow / "runtime" / "results" / "B.json").read_text(encoding="utf-8")
            + (self.workflow / "runtime" / "events.jsonl").read_text(encoding="utf-8"),
        )
        events = (self.workflow / "runtime" / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn('"type":"node_dispatched"', events)
        self.assertIn('"outcome":"succeeded"', events)

    def test_confirmation_response_is_digest_bound(self) -> None:
        graph = json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))
        triage = {
            "blocking_scope": "branch",
            "impacts": ["authority"],
            "affected_nodes": ["E"],
            "no_safe_default_reason": "Remote delivery authority cannot be inferred.",
            "resolution_mode": "resume",
            "request_graph_digest": canonical_graph_digest(graph),
            "authority_capabilities": ["local_write"],
        }
        surface = json.dumps(
            {"question": "Approve delivery?", "alternatives": ["defer"], "risks": ["remote mutation"], "triage": triage},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        request = {
            "schema_version": 2,
            "request_id": "approve-delivery",
            "node_id": "E",
            "digest": "sha256:" + hashlib.sha256(surface).hexdigest(),
            "question": "Approve delivery?",
            "alternatives": ["defer"],
            "risks": ["remote mutation"],
            "triage": triage,
            "status": "pending",
            "created_at": "2026-07-19T00:00:00Z",
            "response": None,
        }
        request_path = self.workflow / "runtime" / "requests" / "approve-delivery.json"
        write_json(request_path, request)
        rejected = subprocess.run(
            [sys.executable, str(CONFIRM), str(self.workflow), "--request-id", "approve-delivery", "--digest", "sha256:" + "b" * 64, "--decision", "approved", "--answer", "yes"],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(rejected.returncode, 0)
        accepted = subprocess.run(
            [sys.executable, str(CONFIRM), str(self.workflow), "--request-id", "approve-delivery", "--digest", request["digest"], "--decision", "approved", "--answer", "yes"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        self.assertEqual(json.loads(request_path.read_text(encoding="utf-8"))["status"], "approved")

    def test_request_triage_rejects_overbroad_branch_and_pauses_only_workflow_scope(self) -> None:
        graph = json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))

        def result(blocking_scope: str, affected_nodes: list[str]) -> dict:
            triage = {
                "blocking_scope": blocking_scope,
                "impacts": ["scope"],
                "affected_nodes": affected_nodes,
                "no_safe_default_reason": "Either choice changes the locked node contract.",
                "resolution_mode": "rebase",
                "request_graph_digest": canonical_graph_digest(graph),
                "authority_capabilities": [],
            }
            surface = json.dumps(
                {"question": "Choose the contract boundary?", "alternatives": ["shared", "local"], "risks": ["contract drift"], "triage": triage},
                sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")
            return {
                "request": {
                    "request_id": f"triage-{blocking_scope}",
                    "digest": "sha256:" + hashlib.sha256(surface).hexdigest(),
                    "question": "Choose the contract boundary?",
                    "alternatives": ["shared", "local"],
                    "risks": ["contract drift"],
                    "triage": triage,
                }
            }

        branch_path = WORKFLOW_RUNTIME.store_request(self.workflow, graph, "C", result("branch", ["C", "E", "F"]))
        self.assertTrue(branch_path.is_file())
        self.assertFalse(WORKFLOW_RUNTIME.has_pending_workflow_request(self.workflow))

        with self.assertRaisesRegex(ValueError, "only the requesting node and its descendants"):
            WORKFLOW_RUNTIME.store_request(self.workflow, graph, "C", result("branch", ["C", "D"]))

        WORKFLOW_RUNTIME.store_request(self.workflow, graph, "C", result("workflow", ["C"]))
        self.assertTrue(WORKFLOW_RUNTIME.has_pending_workflow_request(self.workflow))

        workflow_request = self.workflow / "runtime" / "requests" / "triage-workflow.json"
        value = json.loads(workflow_request.read_text(encoding="utf-8"))
        value["status"] = "approved"
        write_json(workflow_request, value)
        self.assertEqual(WORKFLOW_RUNTIME.workflow_scoped_resumes([("C", workflow_request)]), [("C", workflow_request)])

    def request_for_mode(self, node_id: str, request_id: str, impacts: list[str], mode: str) -> Path:
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        triage = {
            "blocking_scope": "branch",
            "impacts": impacts,
            "affected_nodes": [node_id],
            "no_safe_default_reason": "The decision changes the execution contract.",
            "resolution_mode": mode,
            "request_graph_digest": canonical_graph_digest(graph),
            "authority_capabilities": [],
        }
        question = "Choose the execution contract?"
        alternatives = ["first", "second"]
        risks = ["stale execution"]
        surface = json.dumps(
            {"question": question, "alternatives": alternatives, "risks": risks, "triage": triage},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        return WORKFLOW_RUNTIME.store_request(
            self.workflow,
            graph,
            node_id,
            {"request": {"request_id": request_id, "digest": "sha256:" + hashlib.sha256(surface).hexdigest(), "question": question, "alternatives": alternatives, "risks": risks, "triage": triage}},
        )

    def test_resume_is_invalidated_by_graph_drift(self) -> None:
        graph_path = self.workflow / "graph.json"
        resume_path = self.request_for_mode("D", "resume-d", ["cost_risk"], "resume")
        WORKFLOW_RUNTIME.workflow_state.transition(WORKFLOW_RUNTIME.arg_namespace(graph_path, "D", "waiting_approval"))
        resume = json.loads(resume_path.read_text(encoding="utf-8"))
        resume["status"] = "approved"
        write_json(resume_path, resume)
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["authority_grants"]["D"] = {
            "capabilities": ["local_write"],
            "request_id": "resume-d",
            "request_digest": resume["digest"],
            "granted_at": "2026-01-01T00:00:00Z",
        }
        write_json(runtime_path, runtime)
        changed = json.loads(graph_path.read_text(encoding="utf-8"))
        changed["objective"]["statement"] += " Changed."
        write_json(graph_path, changed)
        self.assertEqual(WORKFLOW_RUNTIME.approved_resumes(self.workflow, self.repo, graph_path), [])
        self.assertEqual(json.loads(resume_path.read_text(encoding="utf-8"))["status"], "invalidated")
        self.assertNotIn("D", json.loads(runtime_path.read_text(encoding="utf-8"))["authority_grants"])

    def test_rebase_confirmation_waits_for_graph_change(self) -> None:
        graph_path = self.workflow / "graph.json"
        rebase_path = self.request_for_mode("D", "rebase-d", ["scope"], "rebase")
        WORKFLOW_RUNTIME.workflow_state.transition(WORKFLOW_RUNTIME.arg_namespace(graph_path, "D", "waiting_approval"))
        rebase = json.loads(rebase_path.read_text(encoding="utf-8"))
        rebase["status"] = "approved"
        write_json(rebase_path, rebase)
        self.assertEqual(WORKFLOW_RUNTIME.approved_resumes(self.workflow, self.repo, graph_path), [])


if __name__ == "__main__":
    unittest.main()
