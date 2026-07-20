---
name: writing-great-skills
description: Audit and improve skills for predictable invocation and execution.
disable-model-invocation: true
---

# Audit a skill for predictability

A skill is predictable when repeated runs follow the same process while adapting outputs to the
task. Read [GLOSSARY.md](GLOSSARY.md) for the authoritative definitions used below.

## 1. Inventory the public contract

Read the complete `SKILL.md`, every context pointer needed by its branches, directly invoked scripts,
agent metadata, and available eval evidence. Record whether the skill is model-invoked or user-
invoked and list each distinct invocation branch.

Complete inventory when every public behavior, dependency, side effect, and validation surface is
accounted for.

## 2. Audit invocation

For a model-invoked skill, front-load one leading word and retain one trigger per distinct branch in
the description. Remove synonymous trigger restatements and body identity from the description.

For a user-invoked skill, set `disable-model-invocation: true` and use a short human-facing
description. If many user-invoked skills create cognitive load, recommend one router skill.

Complete invocation when every intended prompt maps to one skill and overlapping skills have an
explicit routing boundary.

## 3. Audit the information hierarchy

Classify each paragraph as an in-skill step, in-skill reference, or disclosed reference. Keep the
steps every branch needs in `SKILL.md`; place branch-specific facts, examples, schemas, and command
catalogues behind context pointers that state exactly when to read them. Co-locate each concept's
definition, rules, and caveats.

Complete hierarchy when each branch loads only the material it needs and every required external
resource has a reliable pointer.

## 4. Audit execution

Walk each step in order. Require a checkable completion criterion that names the observable state
needed before the next step. Strengthen criteria until they demand all required legwork. Split a
sequence only when an irreducibly fuzzy criterion has demonstrated premature completion.

For reference-only skills, add one exhaustive criterion binding every applicable rule. Confirm that
dependencies exist, commands match their documented interface, and destructive or external actions
have explicit authority gates and positive safe alternatives.

Complete execution when every branch can reach an honest terminal state without inventing missing
policy or silently skipping work.

## 5. Prune language

Apply four sentence-level passes:

1. **Single source of truth:** keep each behavior in one authoritative place.
2. **Relevance:** remove stale or branch-irrelevant sediment.
3. **No-op:** delete instructions that do not change model behavior.
4. **Positive steering:** state the target behavior; reserve prohibitions for hard guardrails and pair
   them with the safe action.

Collapse repeated behavioral explanations into strong pretrained leading words. Prefer imperative,
concrete language, consistent terminology, and repository-discovered policy over provider-, tool-,
branch-, or project-specific assumptions.

Complete pruning when every remaining sentence changes invocation, execution, safety, or output.

## 6. Validate the grade

An **S-grade** skill satisfies all of these:

- invocation branches are distinct and metadata agrees with the body;
- every step and reference-only rule set has a checkable completion criterion;
- context pointers are conditional, direct, and valid;
- public behavior is portable or explicitly scoped by name and description;
- dependencies and authority boundaries are executable;
- wording is concise, positive, consistent, and single-source;
- structural validation passes and realistic forward-tests demonstrate improvement over baseline or
  cover the skill's critical failure modes.

Report findings by severity with exact file evidence, then give every audited skill an explicit pass
or the unmet criterion. The audit is complete only when every selected skill has been evaluated
against every S-grade criterion.
