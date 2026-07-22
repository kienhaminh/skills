#!/usr/bin/env python3
"""Exercise the real Graphflow runner from recursive split through verified Ship."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "workflow-template"
RUNNER = ROOT / "scripts" / "run_workflow.py"
CONFIRM = ROOT / "scripts" / "confirm_workflow.py"
sys.path.insert(0, str(ROOT / "scripts"))

import checkout_guard  # noqa: E402
import evidence_runner  # noqa: E402
import memory_state  # noqa: E402
import progress_state  # noqa: E402
import question_gate  # noqa: E402
from skills.graphflow.evals.fixture_support import approve_manifest, complete_clear_review


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False,
    )
    if completed.returncode:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.stdout.strip()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class RunnerLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.remote = self.root / "remote.git"
        self.workflow = self.root / "workflow"
        self.bin_dir = self.root / "bin"
        self.repo.mkdir()
        self.bin_dir.mkdir()
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "master", str(self.repo)], check=True)
        git(self.repo, "config", "user.name", "Graphflow Eval")
        git(self.repo, "config", "user.email", "eval@graphflow.invalid")
        (self.repo / "seed.txt").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "chore: base")
        hosting_url = "https://example.invalid/acme/portable-repo.git"
        git(self.repo, "config", f"url.{self.remote}.insteadOf", hosting_url)
        git(self.repo, "remote", "add", "origin", hosting_url)
        git(self.repo, "push", "-q", "origin", "master")
        shutil.copytree(TEMPLATE, self.workflow)
        self.configure_agent_adapter()
        self.configure_workflow()
        self.fake_codex = self.make_fake_codex()
        self.make_fake_gh()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def configure_workflow(self) -> None:
        graph_path = self.workflow / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["lifecycle"]["status"] = "ready"
        graph["constraints"]["max_parallel"] = 2
        graph["verification"] = {"outcome": "pending", "claims": []}
        for node in graph["nodes"]:
            if node["kind"] == "expand":
                continue
            node["status"] = "complete" if node["id"] == "P" else "pending"
            node["retry"]["attempts"] = 0
            node["retry"]["last_failure_class"] = None
            if node["id"] != "P":
                node["runtime"].update(
                    agent=None, started_at=None, updated_at=None, completed_at=None,
                    summary=None, tokens_used=0,
                )
        approve_manifest(self.workflow, graph)
        write_json(graph_path, graph)

        plan_path = self.workflow / "integrity" / "verification-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        artifact_by_requirement = {
            "R1": "packages/contracts/src/publish-retry.ts",
            "R2": "apps/server/src/publish/bulk-retry",
            "R3": "apps/web/app/admin/publish-queue/bulk-retry",
            "R4": "apps/server/src/publish/bulk-retry.integration.ts",
            "R5": "apps/server/src/publish/bulk-retry.integration.ts",
        }
        for check in plan["checks"]:
            requirement = check["requirement_ids"][0]
            path = artifact_by_requirement[requirement]
            check.update(
                argv=["python3", "-c", "from pathlib import Path; assert Path('seed.txt').read_text().strip() == 'base'"],
                cwd="repo", env={}, expected_exit=0, timeout_seconds=30,
                watch=[{"root": "repo", "path": path}],
            )
        write_json(plan_path, plan)

        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["question_gate"]["review"] = {
            "status": "required", "artifact": "question-review.json", "digest": None,
            "graph_digest": None, "reviewer_id": None,
        }
        graph["integrity"].update(status="proposed", plan_digest=None, runner_digest=None)
        write_json(graph_path, graph)
        review_path = self.workflow / "question-review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        complete_clear_review(review)
        review["graph_digest"] = question_gate.question_surface_digest(graph)
        review["reviewed_at"] = "2026-07-20T00:00:00Z"
        write_json(review_path, review)
        question_gate.lock(self.workflow)
        write_json(self.workflow / "integrity" / "lock.json", {
            "schema_version": 1, "workflow_id": graph["workflow_id"], "status": "template",
            "plan_digest": None, "runner_digest": None, "contract_digest": None, "locked_at": None,
        })
        evidence_runner.command_lock(self.workflow, self.repo)
        memory_state.command_init(self.workflow, self.repo)
        progress_state.update(self.workflow, "P", "scope_accepted", workspace_ref="primary")
        progress_state.update(self.workflow, "P", "evidence_passed", workspace_ref="primary")
        progress_state.update(self.workflow, "P", "accepted", workspace_ref="primary")

        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["authority"]["local_write"] = True
        runtime["authority"]["network"] = True
        runtime["authority"]["credentials"] = True
        runtime["delivery"] = {
            "schema_version": 1,
            "required": True,
            "adapter": "ship-v1",
            "status": "proposed",
            "remote": "origin",
            "base_branch": "master",
            "head_branch": "graphflow/runner-lifecycle",
            "record": {
                "mode": "no_plan", "active_plan": None, "completed_plan": None,
                "no_plan_reason": "The lifecycle eval is a bounded generated fixture.",
            },
            "commit": {"subject": "feat: ship graphflow lifecycle", "body": "Publish the verified lifecycle fixture."},
            "pull_request": {
                "repository": "example.invalid/acme/portable-repo",
                "title": "feat: ship graphflow lifecycle",
                "body": "## Goal\nShip the runner lifecycle fixture.\n\n## What changed\n- Added the verified generated fixture.\n\n## Verification\n- Graphflow verifier passed.\n",
            },
            "required_capabilities": ["commit", "push", "pull_request", "network", "credentials"],
            "grant": None,
            "manifest": "runtime/delivery/manifest.json",
            "proof": "runtime/delivery/proof.json",
            "request_id": None,
            "failure": None,
            "updated_at": None,
        }
        write_json(runtime_path, runtime)
        checkout_guard.advance(self.workflow, self.repo)

    def configure_agent_adapter(self) -> None:
        adapter = self.workflow / "adapters" / "codex-cli.py"
        adapter.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "assets" / "adapter-templates" / "codex-cli.py", adapter)
        runtime_path = self.workflow / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["agent_adapter"] = {
            "schema_version": 1,
            "protocol": "graphflow-agent-adapter-v1",
            "id": "codex-cli-test-v1",
            "argv": ["python3", "adapters/codex-cli.py"],
            "env_allow": [],
            "resources": [{"path": "adapters/codex-cli.py", "digest": digest(adapter)}],
            "sandbox_modes": ["read-only", "workspace-write"],
            "model_map": {"small": "fake-small", "balanced": "fake-balanced", "frontier": "fake-frontier"},
            "requires_authority": [],
        }
        write_json(runtime_path, runtime)

    def make_fake_codex(self) -> Path:
        path = self.bin_dir / "codex"
        path.write_text(
            """#!/usr/bin/env python3
import json,re,sys
from pathlib import Path

args=sys.argv[1:]
out=Path(args[args.index('--output-last-message')+1])
prompt=sys.stdin.read()

def review():
    def field(name):
        match=re.search(name+r\"='([^']+)'\",prompt)
        if not match: raise RuntimeError(name)
        return match.group(1)
    value={'schema_version':1,'workflow_id':field('workflow_id'),'graph_digest':field('graph_digest'),'methods':['Rumsfeld Matrix','Value of Information','Reversibility','Premortem'],'reviewer':{'agent_id':field('reviewer.agent_id'),'model_class':'small','model_id':'fake-small','independent':True,'context_policy':'fresh-artifacts-only'},'challenges':[{'class':'misread-intent','result':'clear','rationale':'Objective remains bound.'},{'class':'hidden-dependency','result':'clear','rationale':'Handoffs remain closed.'},{'class':'oracle-gap','result':'clear','rationale':'Locked checks are conserved.'}],'findings':[],'status':'passed','reviewed_at':'2026-07-20T00:00:00Z'}
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(value)); return

if '--output-schema' not in args:
    review(); raise SystemExit(0)

workflow=Path(args[args.index('--output-schema')+1]).parents[1]
graph=json.loads((workflow/'graph.json').read_text())
node_id=re.search(r'"node_id":\\s*"([^"]+)"',prompt).group(1)
node=next(item for item in graph['nodes'] if item['id']==node_id)
spec=json.loads((workflow/node['executor']['spec']).read_text())

def base(status,summary):
    return {'schema_version':2,'workflow_id':graph['workflow_id'],'node_id':node_id,'attempt':node['retry']['attempts'],'idempotency_key':spec['idempotency_key'],'status':status,'summary':summary,'outputs':[],'evidence':[],'memory_delta':None,'request':None,'decomposition':None,'usage':{'input_tokens':12,'output_tokens':24}}

def split(parent_value,support,terminal,support_value,terminal_value,support_budget,terminal_budget):
    handoff='handoff-'+node_id.lower().replace('.','-')
    return {'schema_version':1,'contract_change':'structural','reason_class':'complexity','reason':'Use a finite structural split with an explicit handoff.','measure':{'name':'lifecycle-points','parent':parent_value,'children':[{'key':support,'value':support_value},{'key':terminal,'value':terminal_value}]},'terminal_child':terminal,'children':[{'key':support,'title':'Bounded analysis','outcome':'Produce the internal handoff.','operations':['implementation'],'methods':['YAGNI','Contract Testing'],'skills':['implement'],'depends_on':[],'scope':{'read':list(node['scope']['read']),'write':[],'artifacts':[],'decisions':[],'forbidden':list(node['scope']['forbidden'])},'consumes':list(node['consumes']),'outputs':[{'id':handoff,'description':'Bounded decomposition handoff.','artifact':None}],'acceptance':['The bounded handoff is explicit.'],'acceptance_checks':['CHK-R1-CONTRACT'],'budget_tokens':support_budget},{'key':terminal,'title':'Terminal materialization','outcome':'Preserve the parent output contract.','operations':['implementation'],'methods':['Contract Testing','DRY'],'skills':['implement'],'depends_on':[support],'scope':{'read':list(node['scope']['read']),'write':list(node['scope']['write']),'artifacts':list(node['scope']['artifacts']),'decisions':list(node['scope']['decisions']),'forbidden':list(node['scope']['forbidden'])},'consumes':list(node['consumes'])+[handoff],'outputs':list(node['outputs']),'acceptance':list(node['acceptance']),'acceptance_checks':['CHK-R1-CONTRACT'],'budget_tokens':terminal_budget}]}

if node_id=='B':
    value=base('decompose','Split contract work structurally.'); value['decomposition']=split(5,'analyze','materialize',1,3,300,1000)
elif node_id=='B.materialize':
    value=base('decompose','Split terminal work recursively.'); value['decomposition']=split(3,'refine','finish',1,2,300,600)
else:
    for output in node.get('outputs',[]):
        artifact=output.get('artifact')
        if isinstance(artifact,str):
            target=(workflow/artifact) if node_id=='F' else (Path.cwd()/artifact)
            target.parent.mkdir(parents=True,exist_ok=True); target.write_text(node_id+'\\n')
    value=base('succeeded','Completed the bounded node contract.')
    if node_id=='F':
        plan=json.loads((workflow/'integrity/verification-plan.json').read_text())
        first={}
        for check in plan['checks']:
            for requirement in check['requirement_ids']:
                first.setdefault(requirement,check)
        value['verification']={'schema_version':1,'outcome':'pass','challenge_classes':['negative','boundary'],'claims':[{'id':'C-'+requirement['id'],'requirement_id':requirement['id'],'statement':requirement['text'],'state':'verified','confidence':'high','evidence':[{'check':first[requirement['id']]['id'],'artifact':first[requirement['id']]['attestation']}],'limitations':[]} for requirement in graph['objective']['requirements']],'limitations':[]}

out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(value))
""",
            encoding="utf-8",
        )
        path.chmod(0o700)
        return path

    def make_fake_gh(self) -> None:
        state = self.root / "gh-state.json"
        path = self.bin_dir / "gh"
        path.write_text(
            "#!/usr/bin/env python3\n"
            "import json,subprocess,sys\n"
            "from pathlib import Path\n"
            "args=sys.argv[1:]\n"
            f"state=Path({str(state)!r})\n"
            "if args[:2]==['auth','status']: raise SystemExit(0)\n"
            "if args[:2]==['pr','list']: print(state.read_text() if state.exists() else '[]'); raise SystemExit(0)\n"
            "if args[:2]==['pr','create']:\n"
            " head=args[args.index('--head')+1]; base=args[args.index('--base')+1]; title=args[args.index('--title')+1]; body=args[args.index('--body')+1]\n"
            " oid=subprocess.check_output(['git','ls-remote','--heads','origin',f'refs/heads/{head}'],text=True).split()[0]\n"
            " state.write_text(json.dumps([{'url':'https://example.invalid/pull/runner','state':'OPEN','headRefOid':oid,'title':title,'body':body,'baseRefName':base,'headRefName':head}]))\n"
            " print('https://example.invalid/pull/runner'); raise SystemExit(0)\n"
            "if args[:2]==['pr','edit']: raise SystemExit(0)\n"
            "raise SystemExit(2)\n",
            encoding="utf-8",
        )
        path.chmod(0o700)

    def run_workflow(self) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PATH"] = str(self.bin_dir) + os.pathsep + environment.get("PATH", "")
        environment["GRAPHFLOW_CODEX_BIN"] = str(self.fake_codex)
        return subprocess.run(
            [sys.executable, str(RUNNER), str(self.workflow), "--repo-root", str(self.repo)],
            capture_output=True, text=True, check=False, env=environment, timeout=180,
        )

    def approve_ship(self) -> None:
        runtime = json.loads((self.workflow / "runtime.json").read_text(encoding="utf-8"))
        request_id = runtime["delivery"]["request_id"]
        request_path = self.workflow / "runtime" / "requests" / f"{request_id}.json"
        request = json.loads(request_path.read_text(encoding="utf-8"))
        completed = subprocess.run(
            [sys.executable, str(CONFIRM), str(self.workflow), "--request-id", request_id, "--digest", request["digest"], "--decision", "approved", "--answer", "publish exact manifest"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_real_runner_recursive_parallel_verified_ship(self) -> None:
        first = self.run_workflow()
        failure_detail = first.stdout + first.stderr
        if first.returncode:
            failure_detail += "\nGRAPH\n" + (self.workflow / "graph.json").read_text(encoding="utf-8")
            failure_detail += "\nEVENTS\n" + (self.workflow / "runtime" / "events.jsonl").read_text(encoding="utf-8")
            for path in (self.workflow / "runtime" / "agent-events").glob("*.json"):
                failure_detail += f"\n{path.name}\n" + path.read_text(encoding="utf-8")
        self.assertEqual(first.returncode, 0, failure_detail)
        self.assertEqual(json.loads(first.stdout)["status"], "waiting")

        graph = json.loads((self.workflow / "graph.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["B"]["kind"], "expand")
        self.assertEqual(nodes["B.materialize"]["kind"], "expand")
        self.assertEqual(nodes["B.materialize.finish"]["decomposition_bound"]["value"], 2)
        self.assertTrue(all(node["status"] in {"complete", "expanded"} for node in graph["nodes"]))
        self.assertEqual(graph["verification"]["outcome"], "verified")
        self.assertEqual({claim["requirement_id"] for claim in graph["verification"]["claims"]}, {"R1", "R2", "R3", "R4", "R5"})
        self.assertTrue((self.workflow / "integrity" / "reviews" / "F.json").is_file())

        events = [json.loads(line) for line in (self.workflow / "runtime" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        dispatch = [event["node_id"] for event in events if event.get("type") == "node_dispatched"]
        c_index, d_index = dispatch.index("C"), dispatch.index("D")
        finish_positions = [index for index, event in enumerate(events) if event.get("type") == "node_finished"]
        dispatch_positions = {event["node_id"]: index for index, event in enumerate(events) if event.get("type") == "node_dispatched"}
        self.assertLess(dispatch_positions["C"], min(position for position in finish_positions if position > dispatch_positions["C"]))
        self.assertLess(dispatch_positions["D"], min(position for position in finish_positions if position > dispatch_positions["C"]))
        self.assertEqual(abs(c_index - d_index), 1)

        self.approve_ship()
        second = self.run_workflow()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(json.loads(second.stdout)["status"], "complete")
        runtime = json.loads((self.workflow / "runtime.json").read_text(encoding="utf-8"))
        self.assertEqual(runtime["delivery"]["status"], "published")
        proof = json.loads((self.workflow / "runtime" / "delivery" / "proof.json").read_text(encoding="utf-8"))
        remote = git(self.repo, "ls-remote", "--heads", "origin", "refs/heads/graphflow/runner-lifecycle")
        self.assertTrue(remote.startswith(proof["release_sha"]))


if __name__ == "__main__":
    unittest.main()
