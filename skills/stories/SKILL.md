---
name: stories
description: Slice an agreed plan into an epic and behavior-focused stories with observable acceptance criteria, reconciled against repository-owned domain rules.
---

# Turn a plan into user stories

Produce one transient story artifact that translates implementation intent into observable user
value. Preserve the source plan and implementation.

## 1. Read the contract

Use the named plan or the repository's active planning source. Map its goal, current state, decisions,
steps, verification, exclusions, and open questions. Read the authoritative domain/product rules when
present; use the plan alone and state the limitation when durable rules are absent.

Complete this phase when every plan section has a destination in the story artifact or an explicit
reason it does not apply.

## 2. Check the domain

Use actors and value named by the plan or durable domain source. When proposed behavior contradicts a
binding rule:

1. mark the affected story `Open` or `Contradicts domain`;
2. include the conflict in a `Domain check` section;
3. preserve both source documents for maintainer resolution.

Complete the check when every relevant rule is satisfied, contradicted, or named as unavailable.

## 3. Slice vertically

Produce one epic and usually three to seven stories. Each story names who observes the change, what
they can do afterward, and why it matters.

- Merge implementation steps that deliver one observable capability.
- Split independently valuable behavior.
- Keep enabling groundwork inside the capability it enables.
- Use a developer actor only for a developer-experience outcome.
- Carry dependencies, constraints, and unresolved questions explicitly.
- Keep excluded scope out of the backlog.

Complete slicing when every plan step maps to exactly one story or to named enabling groundwork.

## 4. Write acceptance criteria

Give each story three to six criteria at the actor's altitude. Include meaningful failure behavior
when the plan or durable rules define it. When failure semantics are missing, add an `Open` question
instead of inventing status codes, messages, permissions, retries, or fallback behavior. Describe
observable outcomes; keep files, tables, framework calls, and generic quality gates in constraints or
implementation notes. Preserve technical vocabulary only when the actor directly uses the API, tool,
or command.

Use this minimum shape:

```markdown
# Epic: <observable capability>
Source: <plan path or request>. Generated: YYYY-MM-DD.

## Value
## Not included
## Domain check
## Stories
### S1 — <observable capability>
**As a** <actor>, **I want** <capability>, **so that** <value>.
Acceptance criteria:
- [ ] <observable behavior>
Constraints: <settled decision; omit if none>
Depends on: <S-id or none>
Open: <unresolved question; omit if none>
Contradicts domain: <rule; omit if none>

## Traceability
| Story | Plan source | Plan verification |
| --- | --- | --- |
```

Write to the repository's existing story/backlog location and language. If none exists, return the
artifact in chat unless the user requested a file.

The skill is complete when every story has a real actor, value, observable criteria, and traceable
source; defined failure behavior is preserved and missing failure contracts remain visible as `Open`;
exclusions, dependencies, questions, and domain conflicts are accounted for. Invoke `$tdd` only when
the user requests tests for a selected story.
