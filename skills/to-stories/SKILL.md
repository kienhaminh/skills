---
name: to-stories
description: Convert a plan into an epic and behaviour-sliced user stories with acceptance criteria under docs/plans/stories/. Use when the user asks for user stories, backlog items, tickets, an epic, or a breakdown of work implied by a plan. Ground stories in docs/design/domain.md and flag conflicts with established business rules.
---

# Plan to user stories

Turn implementation intent into observable user value. Produce one transient story file; do not
rewrite the source plan or implementation code.

## Read the inputs

Use the named plan or select one from `docs/plans/active/`. If several candidates exist and the
request does not identify one, ask which plan to use. Map non-standard plans onto:

- **Goal** -> epic and value.
- **Out of scope** -> explicit exclusions.
- **Current state** -> user pain and `so that` clauses.
- **Decisions** -> story constraints.
- **Steps** -> coverage and dependencies.
- **Verification** -> evidence to translate into observable acceptance criteria.
- **Open questions** -> `Open` notes on affected stories.

Read `docs/design/domain.md` for durable actors, concepts, and business rules. If it is missing or
too thin, proceed from the plan and state the limitation. Do not read code to settle feasibility and
do not treat older story files as authoritative.

## Check the domain

Use real actors and value named by the plan or domain. When a proposed behaviour contradicts a
documented business rule:

1. mark the affected story with `Open:` or `Contradicts domain:`;
2. include the conflict in `## Domain check`;
3. leave the rule and plan unchanged for the maintainer to resolve.

Note lasting new behaviour that should later be folded into `domain.md` with `$sync-docs`.

## Slice by behaviour

Produce one epic and usually 3-7 vertical stories. A story must name who notices the change and what
they can do afterwards.

- Merge implementation steps that deliver one observable capability.
- Split a step only when it contains independently valuable behaviours.
- Keep groundwork inside the acceptance criteria of the capability it enables.
- Use a developer as actor only when developer experience is the deliverable.
- Carry dependencies, settled constraints, and unresolved questions explicitly.
- Never turn an out-of-scope item into a story.

## Write acceptance criteria

Write 3-6 criteria per story at the actor's altitude, including a meaningful unhappy path.

- Describe observable behaviour, not files, tables, guards, framework calls, or internal steps.
- Translate engineering verification into what the actor experiences; do not copy it verbatim.
- Keep technical terms only when the actor directly uses that API, tool, or command.
- Do not include generic gates such as "tests pass" or invent repository details absent from the
  plan.
- Put settled implementation choices in `Constraints`, not in the story's value statement.

## Write the story file

Write English to `docs/plans/stories/<plan-slug>.md`:

```markdown
# Epic: <capability from Goal>
Source: [`plans/active/<slug>.md`](../active/<slug>.md). Generated: YYYY-MM-DD.
> Transient: discard with the plan. Durable behaviour belongs in `design/domain.md`.

## Value
<Goal + Current state, grounded in the domain>

## Not included
- <each out-of-scope item>

## Domain check
- <conflicts, limitations, or "No contradictions found.">

## Stories
### S1 - <observable capability>
**As a** <actor>, **I want** <capability>, **so that** <value>.
Acceptance criteria:
- [ ] <observable behaviour>
Constraints: <settled decision; omit if none>
Depends on: <S-id or none>
Open: <unresolved question; omit if none>
Contradicts domain: <rule; omit if none>

## Traceability
| Story | Plan steps | Plan verification |
| --- | --- | --- |
```

The traceability table must account for every plan step. Identify groundwork with no standalone
user value rather than inventing a horizontal story for it.

## Verify and hand off

Read the generated file back and confirm:

- every story has a real actor, value, criteria, and traceable plan source;
- criteria stay at the actor's altitude and include relevant failure behaviour;
- exclusions, constraints, dependencies, open questions, and domain conflicts remain visible;
- the plan is untouched and no unsupported repository detail was invented.

Report the output path and only the judgement calls the user should review: merged or split steps,
inferred unhappy paths, unresolved questions, and domain conflicts. Invoke `$to-tdd` only when the
user asks to turn a selected story into failing tests.
