---
name: debugging
description: Diagnose local failures in the Vietnam monorepo through evidence-based root-cause analysis. Use for bugs, failing tests, runtime errors, data anomalies, stuck jobs, environment problems, and complex, intermittent, or expensive-to-reproduce failures.
---

# Debugging

Follow `docs/DEBUG.md` for project-specific procedures, evidence sources, commands, and known traps. Do not invent a separate reproduction method.

Reason internally: verify the symptom, trace the first divergence from expected behavior, identify the violated invariant, compare competing hypotheses, seek discriminating evidence, and derive the causal chain.

If reproduction is costly or unreliable, trace backward through callers, contracts, state transitions, and async boundaries. Inspect concurrency, retries, timing, caches, configuration, and partial failures. Mark conclusions as analysis-derived and lower confidence when runtime evidence is missing.

Rules:

- Trust current code and runtime evidence. Separate facts, inferences, and unknowns.
- Distinguish root cause from trigger, contributing factor, and downstream symptom.
- Try to falsify the leading hypothesis; explain the strongest rejected alternative.
- Diagnose only. Do not propose or implement a fix unless separately requested.

Report in at most 180 words unless the user requests detail:

- diagnosis and confidence;
- evidence-backed causal chain and violated invariant;
- strongest rejected alternative;
- remaining uncertainty and evidence needed for confirmation.

Do not narrate the process, restate the prompt, or list every inspected file.
