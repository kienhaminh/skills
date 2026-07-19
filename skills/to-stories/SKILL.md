---
name: to-stories
description: Convert a plan document (docs/plans/active/*.md, or any plan-shaped doc) into an epic plus behaviour-sliced user stories with acceptance criteria, written to docs/plans/stories/<plan-slug>.md. Grounds the stories in docs/design/domain.md and flags anything that contradicts an established business rule. Use this whenever the user asks to turn a plan into user stories, backlog items, tickets, an epic, or "chuyển plan thành user story" — and also when they hand you a plan file and ask what work it implies, how to break it down, or how to slice it for a backlog, even if they never say the words "user story".
---

# Plan → user stories

A plan answers *how we will build it*. A user story answers *what someone can do once it exists,
and how we know it works*. Converting between them is not reformatting — it is a change of
viewpoint, and that is where the value is. A conversion that renames each implementation step
into "As a developer, I want to add a status column" has produced nothing: it is the plan with
extra words. Read the plan for the **behaviour it will produce**, then slice that behaviour.

Two things this skill deliberately does *not* do, both for the same Agile reason — a story is an
invitation to a conversation, not a contract, and its "how" is settled later with the team:

- **It does not read the code to check feasibility.** Whether a story is buildable against the
  current codebase is a separate, collaborative step (backlog refinement / Definition of Ready),
  not part of writing the story. Auditing code here produces confident-sounding stories in exactly
  the places the plan is vaguest — the opposite of useful. Infer from the plan and the domain, and
  flag what you can't settle as `Open`.
- **It does not treat old stories as a source of truth.** Stories are transient: they exist to
  drive one plan's work and are thrown away when it is done (they move to `completed/` with the
  plan). What lasts is the code and the durable business description in
  [`docs/design/domain.md`](../../../docs/design/domain.md). So don't reconcile against sibling
  story files — reconcile against the domain.

## Input

Usually `docs/plans/active/<slug>.md`. Repo plans follow [`docs/PLANS.md`](../../../docs/PLANS.md):
`Goal`, `Out of scope`, `Current state`, `Decisions`, `Steps`, `Verification`, `Open questions`.
Small plans merge sections; only Goal / Out of scope / Steps / Verification are guaranteed.

If the user names no file, look in `docs/plans/active/` and ask which one if several exist.
Plans elsewhere (a pasted doc, a file outside the repo) work too — map whatever headings exist
onto the roles below and note in your summary which inputs were missing.

Read each section for what it uniquely gives you:

| Section | What it feeds |
| --- | --- |
| Goal | The epic. It already states the capability that will exist afterwards. |
| Out of scope | The epic's "Not included" list — carried over verbatim, so nobody re-adds it as a story. |
| Current state | The "so that" clauses. It says what hurts today; that pain is the story's value. |
| Decisions | Constraints inside acceptance criteria (settled tech choices are not stories to debate). |
| Steps | Which stories are technically possible, and the ordering/dependencies between them. |
| Verification | The best acceptance criteria in the file — already concrete and checkable. Reuse them. |
| Open questions | Story-level `Open` notes, or a reason to leave a story deliberately un-sliced. |

## Ground against the domain, and flag contradictions

Before writing, read [`docs/design/domain.md`](../../../docs/design/domain.md) — the durable
description of what the system does and the rules it must obey. It does two jobs here:

- **Anchors value.** A story's "so that" should trace to value the domain (or the plan's Current
  state) actually describes, and its actors should be the real ones the domain names (admin,
  agent, reader, web contributor), not an invented "developer". If a "so that" traces to nothing
  in either place, that is a sign the slice is implementation, not behaviour.
- **Catches contradictions.** If the plan implies behaviour that breaks a domain rule — e.g. an
  agent publishing without admin approval, or a published snapshot being mutated in place — say so
  **explicitly**, both on the affected story (an `Open:` or a `⚠ Contradicts domain:` line) and in
  your summary to the user. Do **not** silently encode the contradiction as an accepted story, and
  do **not** quietly "fix" it to match the domain. Whether a rule changes is the maintainer's
  decision; your job is to make the clash visible.

If `domain.md` is absent or too thin to ground a given story, note that and proceed from the plan
alone — don't block. And if the plan settles genuinely new *lasting* behaviour that domain.md
doesn't yet mention, note (in your summary) that it belongs in domain.md, so the knowledge
outlives these disposable stories.

## Slicing

One plan → one epic + N stories. Aim for 3–7 stories; more than ~8 usually means you sliced
by step, fewer than 3 that you merged distinct behaviours.

**Slice by change in observable behaviour, not by file touched.** Ask of each candidate: *who
notices when this ships, and what can they now do?* If the honest answer is "nobody, it's
groundwork", it is not a story — it is acceptance criteria belonging to the story it unblocks.

The actors are whoever the domain has: an admin, an agent over MCP, a wiki reader, a web
contributor. "As a developer" is almost always a signal you sliced by implementation — it is
legitimate only when the developer experience *is* the deliverable (a `pnpm dev` change, a script
someone runs).

Steps 1–3 of a plan often collapse into a single story, because a user sees one new capability
whether it took one file or five. Conversely one step can split into two stories when it
carries two independently valuable behaviours (e.g. "job runs" and "operator can see it ran").

Vertical slices beat horizontal ones: prefer "an admin can publish one draft end-to-end" over
"the DB schema exists" + "the API exists" + "the UI exists" — the latter three ship value only
when all three land, so they are one story with three criteria.

## Acceptance criteria

An acceptance criterion states, in the actor's own terms, something they can observe is true when
the story is done. The test is altitude: **write what the actor experiences, never how the system
delivers it.** A human admin experiences *"I'm not signed in, so I can't publish, and nothing is
saved"* — not *"the endpoint returns 401"*. A reader experiences *"I only ever see reviewed,
published pages"* — not *"the route reads the `wiki_snapshot` table"*. The endpoint, the status
code, the table, the guard, the framework call, the shell command are all *how* — they belong to
refinement and implementation, and they leave the story. This matters because development exists to
solve a business problem; a story whose criteria are a list of endpoints and rows has quietly
turned back into the engineering plan it came from, and lost the one viewpoint it was meant to add.

So do **not** lift the plan's `Verification` bullets verbatim. In this repo they are written as
engineering checks — endpoints, status codes, DB rows, `pnpm test` — which is the plan's altitude,
not the story's. Translate each one *up* to what the actor would notice:

| Plan verification (how) | Acceptance criterion (what the actor sees) |
| --- | --- |
| `POST /admin/publish/drafts` without a JWT → 401, no row | Someone not signed in as the admin cannot create a draft — the attempt is refused and nothing is saved. |
| Publish → new `wiki_snapshot` row, `/en/wiki/<slug>` renders it | After the admin publishes, the reviewed content becomes the public page, in both languages. |
| Entity with a draft but no snapshot → 404 | A reader never lands on a page that was drafted but never approved. |
| `pnpm --filter @vietnam/server test` stays green | *(dropped — an engineering gate, true of every story, not a user-facing outcome)* |

The one exception is an actor who is genuinely technical: an agent's MCP tool, a developer's
`pnpm dev`. There the tool or command *is* that actor's experience, so naming it is the correct
altitude, not leakage. The test is always the same question: is this term part of what the actor
does, or below it?

Because this skill does not read the code, also don't invent repo specifics — a file path, a
column name — the plan never states; a criterion that names `apiKeys.expiresAt` when the plan
didn't is a guess in the costume of a fact. Write the behaviour ("an expired key is rejected") and
let refinement bind it.

3–6 criteria per story, including the unhappy path where one exists (bad input, missing
permission, duplicate submit) — the plan often omits these, and surfacing them is a large part of
what this conversion is for. Settled design decisions from the plan still have a home — the story's
`Constraints` line — so demoting them out of the criteria doesn't lose them.

## Output

Write to `docs/plans/stories/<plan-slug>.md`, reusing the plan's slug (`wiki-publish-phase-1.md`
→ `docs/plans/stories/wiki-publish-phase-1.md`). Create the directory if absent. English, like
every doc in this repo — even when the conversation is in Vietnamese. This file is transient: it
lives beside the active plan and is discarded when the plan moves to `completed/`.

```markdown
# Epic: <capability, from the plan's Goal>

Source: [`plans/active/<slug>.md`](../active/<slug>.md). Generated: YYYY-MM-DD.
> Transient: discard with the plan when it completes. Durable behaviour belongs in
> [`design/domain.md`](../../design/domain.md).

## Value
One paragraph, from Goal + Current state, anchored to domain.md: what someone can do afterwards
that they can't today.

## Not included
- <each Out of scope item, with its reason>

## Domain check
- <any story that contradicts a domain rule, named here; or "No contradictions with domain.md.">

## Stories

### S1 — <short title>
**As a** <real actor from the domain>, **I want** <capability>, **so that** <value traceable to Current state or domain.md>.

Acceptance criteria:
- [ ] <checkable behaviour>
- [ ] <checkable behaviour>

Constraints: <settled Decisions binding this story; omit the line if none>
Depends on: <S-id, or "none">
Open: <unsettled question blocking this story; omit the line if none>
⚠ Contradicts domain: <the rule this story would break, if any; omit the line if none>

### S2 — ...

## Traceability
| Story | Plan steps | Plan verification |
| --- | --- | --- |
| S1 | 1, 2 | bullet 1 |
```

The traceability table is what makes the conversion auditable: it proves every step landed in
some story and every story came from the plan. If a step maps to no story, either the plan has
work with no user-visible outcome (say so explicitly — it is usually a criterion you dropped),
or you missed a slice.

## Worked example

From the `Run the ingestion worker in pnpm dev` plan in `docs/PLANS.md`:

**Bad — sliced by step, so the reader learns nothing new:**
> S1 — As a developer, I want to add a `dev:worker` script to `apps/server/package.json`, so
> that the script exists.

The plan already said that, in fewer words. There is no actor, no value, and "the script exists"
is not a behaviour anyone can observe.

**Good — sliced by behaviour, criteria at the actor's altitude:**
> ### S1 — Queued jobs process during local development
> **As a** developer running the stack locally, **I want** the ingestion worker to run under
> `pnpm dev`, **so that** jobs I enqueue are processed instead of sitting in the queue silently.
>
> Acceptance criteria:
> - [ ] Running `pnpm dev` brings the worker up alongside the API and web app, and it says plainly whether it's alive.
> - [ ] A job I enqueue while developing actually runs and finishes, with no separate build step.
> - [ ] Editing ingestion code takes effect on the next job without a manual restart.
>
> Constraints: second `nest start --entryFile worker` invocation (`ts-node-dev` rejected).
> Depends on: none
> Open: whether pg-boss tolerates API and worker both registering for the same queue.

Note what happened: three plan steps became one story, because a developer experiences one new
capability; the plan's Decision became a Constraint rather than a story; the Open question rode
along with the story it blocks instead of being lost. The actor here is a developer and the
command `pnpm dev` is genuinely their experience, so it stays — but the criteria still speak to
what the developer *notices* (the worker is up, the job finishes, edits take effect), not to
process counts or pg-boss log lines, which are how you'd verify them, not the point.

## Before you finish

Read the file back once with fresh eyes and check:

- Every story names an actor from the domain — or has a real reason to be "a developer".
- No criterion for a human actor names an endpoint, status code, DB table/column, guard, or shell command — that is *how*, not *what*; translate it up or drop it. Technical terms survive only where the actor is technical (an agent's tool, a developer's command).
- No pure engineering gate ("tests stay green", "typecheck passes") sits among the acceptance criteria, and no criterion invents a repo specific the plan didn't state.
- Every plan step appears in the traceability table.
- Nothing from `Out of scope` reappeared as a story.
- Any clash with a domain rule is flagged, not silently resolved or silently accepted.
- The plan itself stays untouched: this skill produces a new file, it does not rewrite the plan.

Then tell the user where you wrote it and flag the judgement calls worth their attention — steps
you merged, unhappy paths you invented, domain contradictions you surfaced, and anything in the
plan too vague to slice. Those are the parts they need to correct; the rest is mechanical.
