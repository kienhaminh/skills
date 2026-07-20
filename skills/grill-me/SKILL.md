---
name: grill-me
description: Turn a rough software feature request into one codebase-grounded implementation brief. Use for feature pitches, vague product requirements, solution exploration, or explicit “grill me” requests before coding; use $brainstorming for non-implementation questions.
---

# Grill a feature brief

Use **Grill → Ground → Branch → Kill → Write**. Produce a vetted implementation brief; leave
production code and commits untouched.

## Calibrate

Scale depth with ambiguity, blast radius, and irreversibility:

- **Light:** zero to two pivotal questions, two or three directions, compact risks.
- **Full:** cross-boundary, contract, schema, or hard-to-reverse work. Read
  [playbook.md](references/playbook.md) first.

Complete calibration when the requested behavior, likely change surface, and depth are explicit.

## Execute

1. **Grill.** Skim likely owners and use the Rumsfeld matrix to expose missing goals, scope,
   constraints, and a single observable Done test. Ask only pivotal questions that the checkout
   cannot answer; use the available user-input mechanism with concrete repo-grounded options and one
   recommendation. Complete when every design-changing unknown is answered or visibly parked.
2. **Ground.** Verify the source root, version/provenance marker, local change state, authoritative
   instructions, and the user's premise. For Git repositories, include branch or commit and dirty
   state; for non-Git sources, record the available archive, package, revision, or timestamp and its
   limitations. Cite current-state claims with `file:line` or command evidence. Complete when the
   owners, consumers, constraints, provenance, and known debt relevant to the request are accounted
   for.
3. **Branch.** Create two or three materially different directions in Light mode and three to five in
   Full mode, using minimal/YAGNI, first principles, extension, inversion, and reuse/buy as lenses.
   Complete when each direction changes a real decision rather than paraphrasing another.
4. **Kill.** Pre-mortem each direction, score goal fit, scope fit, effort, and reversibility, then
   retain two or three. Present one recommendation for user selection. Complete when the chosen
   direction and rejected alternatives have evidence-backed reasons.
5. **Write.** Use [template.md](references/template.md). Trace blast radius and apply FMEA-lite with
   likelihood, impact, treatment, and detection. A high-likelihood/high-impact risk changes the
   design before handoff.

Return the brief in chat by default. When the user explicitly requests a file, use the repository's
existing planning location and language or confirm the proposed path when no convention exists.
Record assumptions, rejected directions, and parked expansions.

The skill is complete when one chosen direction has owners, ordered changes, a Done test, risks with
detection, and every material unknown is resolved or explicitly marked.
