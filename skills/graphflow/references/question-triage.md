# Question triage — Rumsfeld Matrix + Value of Information + Reversibility

Ask only when the answer can materially change the contract and no evidence-backed reversible default exists.

## Preflight gate

Classify known unknowns before `ready`:

| Class | Rule |
| --- | --- |
| Pivotal | Objective, acceptance, scope, authority, intent baseline, oracle, material cost-risk, or irreversible action: resolve before `ready` |
| Local | Evidence-backed and reversible: choose the safest default, record the assumption and evidence in shared memory, continue |
| Branch | Material only to one branch: block that node and descendants; keep independent frontiers running |
| Optional | Non-required: move to `optional_work`; never ask or block completion |

Maintain root `question_gate` with the exact named methods, `status`, known unresolved pivotal questions, and a locked independent review. Give a fresh low-cost challenger only the objective, trust-order artifacts, approved prototype, graph contract, and output schema—never coordinator reasoning. Require **Premortem** challenges for misread intent, hidden dependency, and oracle gap. Lock with `question_gate.py`; `executable` and `complete` require a current review, `status: clear`, and an empty pivotal list.

## Decision rule

```text
Ask iff material impact
AND no evidence-backed reversible default exists
AND the answer changes a node contract or graph baseline.
```

Do not ask for preferences discoverable from the approved prototype, repository source of truth, existing contract, or a machine oracle. Do not silently assume any authority or irreversible choice.

## Runtime request

For a newly discovered material question, return `waiting_user` or `waiting_approval` with the standard digest-bound request plus:

```json
{
  "triage": {
    "blocking_scope": "branch",
    "impacts": ["scope"],
    "affected_nodes": ["C", "E"],
    "no_safe_default_reason": "Either choice changes the approved API contract.",
    "resolution_mode": "rebase",
    "request_graph_digest": "sha256:<current semantic graph>",
    "authority_capabilities": []
  }
}
```

`blocking_scope` is `branch` or `workflow`. Impacts are limited to `objective`, `acceptance`, `scope`, `authority`, `intent_baseline`, `verification_oracle`, `cost_risk`, or `irreversible_action`. Include the requesting node in `affected_nodes`. Use `rebase` for objective/acceptance/scope/intent/oracle changes; use `resume` only when the current graph remains valid. `request_graph_digest` binds that choice to the exact semantic graph. Authority requests list only capabilities already declared by the executor.

The runner validates this metadata and persists one digest-bound request. `branch` releases the waiting node and continues independent ready frontiers; `workflow` pauses dispatch and resumes that node alone. `resume` is invalidated if the graph changes. `rebase` cannot resume until the graph changes and executable, memory, question-review, oracle, and executor locks pass. After confirmation, record the resulting decision or assumption through a scoped memory delta; never store the conversation.
