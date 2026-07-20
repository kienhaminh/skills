---
name: debugging
description: Diagnose software failures through evidence-based root-cause analysis. Use for bugs, failing tests, runtime errors, data anomalies, stuck jobs, environment failures, and intermittent or expensive-to-reproduce incidents.
---

# Diagnose the first divergence

Read the repository's debugging instructions and known-failure records when present; repository-
specific procedures own commands and evidence sources.

Verify the symptom, find the first divergence from expected behavior, identify the violated
invariant, compare competing hypotheses, seek discriminating evidence, and derive the causal chain.
When reproduction is costly, trace backward through callers, contracts, state transitions, async
boundaries, concurrency, retries, caches, configuration, and partial failures.

Keep facts, inferences, and unknowns distinct. Separate root cause from trigger, contributing factor,
and downstream symptom. Try to falsify the leading hypothesis and explain the strongest rejected
alternative. Runtime evidence supports direct conclusions; static-only reasoning receives lower
confidence and an explicit confirmation path.

When available evidence cannot distinguish the surviving hypotheses, return `inconclusive` with the
ranked candidates, shared evidence, and smallest discriminating observation still needed. An
inconclusive result names no root cause.

This skill's deliverable is diagnosis. Implement or recommend a fix only when the user separately
authorizes that scope.

Report in at most 180 words unless detail is requested:

- diagnosis and confidence;
- evidence-backed causal chain and violated invariant;
- strongest rejected alternative;
- remaining uncertainty and the exact evidence needed to close it.

Diagnosis is complete when one causal chain explains the observed symptom, survives the strongest
available falsification attempt, and every material uncertainty is named. The inconclusive branch is
complete when every surviving hypothesis and the exact evidence needed to distinguish them are named
without promoting one to a diagnosis.
