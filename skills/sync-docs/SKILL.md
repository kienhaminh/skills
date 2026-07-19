---
name: sync-docs
description: Reconcile the repo's durable business docs (mainly docs/design/domain.md) with what the code actually does, and fold a finished plan's lasting behaviour back into them so the next session inherits it. Use when the user asks to "sync docs", "đồng bộ tài liệu", "cập nhật tài liệu với code", fold a completed plan into the docs, or check whether the business docs still match the code — and proactively right after finishing a plan or a behaviour-changing task, when the durable change is freshest and easiest to lose.
---

# Sync durable docs with the code

Plans and stories are disposable — they drive one task and are thrown away when it lands. What
outlives them is the code and the durable business description in
[`docs/design/domain.md`](../../../docs/design/domain.md): the file an agent reads at the start of
a fresh session to learn *what this system does and the rules it must obey*. When a task changes
that lasting behaviour and nobody records it, the knowledge dies in a commit diff. This skill keeps
`domain.md` honest against the code and harvests lasting decisions before they vanish. It is the
executor of the principle `to-stories` only notes — "feed durable behaviour back to domain.md".

Because `domain.md` is read as truth by every later session, a wrong edit poisons all of them. So
the whole skill turns on one distinction (below), and the nuances live in
[`references/reconciliation.md`](references/reconciliation.md) — read it whenever a discrepancy is
non-trivial or you're unsure how to phrase an edit.

## Read → analyse → compare → *then* write

Never write before you understand. The order is not optional: first read the doc and the code,
work out what each currently claims, compare them, and only once you know exactly what drifted do
you touch anything. Writing first is how a wrong edit gets in.

**Read by the map, not by the pound.** Every durable doc here carries a short summary / table of
contents at the top. That header *is* the whole document in miniature — read it to see everything
the doc covers, then follow it to the specific sections you need and read those in full. Do **not**
pull the entire file into context: these docs grow, most of any file is irrelevant to a given
change, and the TOC exists precisely so you can navigate instead of loading. Reading the TOC plus
the sections it points you to is how you "read the whole document".

**Keep the map current.** Whenever you edit or create a durable doc, refresh its top-of-file
TOC/summary so the next session can still navigate by it — a TOC that no longer matches the body
has lost the one thing that makes the doc cheap to read. If a durable doc has no TOC yet, add one
when you touch it.

## Two modes — know which you're in

- **Post-task fold.** You just implemented something this session, or the user says "update the
  docs now that X is done". The code you watched land *is* the new truth. Use the doc's TOC to find
  the section(s) your change touches, read those in full, compare them with the code you wrote,
  fold that one change in, and stop; don't re-audit the repo.
- **Cold audit.** Invoked on its own ("sync docs", "are the docs still right?"). You don't yet know
  what drifted, so find it: scan [`docs/plans/completed/`](../../../docs/plans/completed/) for a
  finished plan whose durable outcome never reached `domain.md`, then use `domain.md`'s TOC to
  enumerate every claim it makes — rules, actors, concepts — and confirm each still holds in the
  code, citing evidence (`file.ts:line` or a command's output), never "it seems to". Then reconcile.

## The one rule that keeps this safe

Split every discrepancy into two kinds, handled oppositely:

- **Descriptive / additive** (a new concept, a changed capability, a renamed step) → **update the
  doc to match the code.** The code is truth and the doc fell behind. This is the common case.
- **A documented invariant is contradicted** (`domain.md`'s *Business rules* section — e.g. *only
  the admin publishes*) → **flag it; never rewrite the rule to match the code.** A violated
  invariant is far more likely a bug or an unratified design change than a reason to edit the rule;
  silently matching the doc to it launders the bug into the source of truth. State it with
  evidence, say which side you think is wrong, and leave the decision to the maintainer.

When unsure which kind a change is, treat it as an invariant and ask.

## Where it goes

Default: extend `domain.md` in place. The repo was recently reorganised and discourages new loose
docs, so **don't scaffold empty files**. Keep the writing at business altitude — no file paths or
table names (those drift and belong in `architecture/`) — and leave a short provenance trace (plan
slug + date), matching `domain.md`'s existing convention. When and why to propose a *new* durable
doc is covered in [`references/reconciliation.md`](references/reconciliation.md).

## Output

Edit the doc(s), then give the user a short summary: what you **folded**, what you **flagged** for
their decision (invariant contradictions — not written), and what you **checked and found still
accurate**. "Docs match the code, nothing to fold" is a valid, useful result — don't invent edits.
The summary template and the finish checklist are in
[`references/reconciliation.md`](references/reconciliation.md).
