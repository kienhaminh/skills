---
name: sync-docs
description: Reconcile durable documentation with implemented behavior. Use for read-only code-versus-doc audits, completed-plan folding, or authorized post-implementation documentation updates; report descriptive drift and escalate binding-rule contradictions.
---

# Synchronize durable documentation

Keep the repository's durable description truthful without turning implementation defects into new
rules.

## 1. Find the source of truth

Read repository instructions and any documentation index or trust order. Identify the durable owner
for the changed behavior—domain, product, architecture, API, runbook, or another established file.
Use its summary or table of contents to select the relevant sections, then read those sections in
full. Read code, executable configuration, tests, and completed task records that can prove the
current behavior.

When no durable owner or trust order exists, return the evidence-backed drift inventory and propose
the narrowest owner with its scope. Create that owner only with user authorization; the absence of a
docs system is an honest terminal state, not permission to invent one.

Complete discovery when the owning document—or the confirmed absence of one—implemented behavior,
and evidence paths are explicit.

## 2. Select the mode

- **Audit:** enumerate the durable document's claims and reconcile each with current code or runtime
  evidence. Return a drift inventory without editing files.
- **Post-task fold:** when the user authorized documentation updates, compare the just-implemented
  behavior with the sections it affects and fold only that durable change.

Use completed task records as leads rather than proof. Complete selection when the claim set, audit
boundary, and write authority are listed.

## 3. Classify every discrepancy

- **Descriptive drift:** new capability, renamed concept, changed sequence, or corrected factual
  description. In Audit mode, report the exact proposed correction; in Post-task fold mode, update
  the document to match proved implementation.
- **Binding-rule contradiction:** implementation violates a documented invariant, policy, or business
  rule. Preserve the rule, report the contradiction with evidence, and request a maintainer decision.
- **Unverified:** available evidence cannot decide which side is correct. Preserve both and name the
  evidence needed.

Treat ambiguous discrepancies as binding until the owner resolves them. Complete classification when
every observed mismatch has exactly one category and evidence.

## 4. Return or write at the owner's altitude

In Audit mode, return the claim inventory, discrepancy class, evidence, and proposed wording in chat.
In Post-task fold mode, extend the existing durable owner. Preserve its vocabulary, structure,
language, and provenance convention. Describe behavior rather than filenames or table layouts unless
the owner is explicitly technical reference. Refresh the document's summary or table of contents
after structural edits.

Complete the skill when every scoped claim is accurate, contradicted, or explicitly unverified;
internal links resolve; and the handoff lists what was folded, what needs a decision, and what was
checked and remained accurate. A no-change result is valid when evidence shows no drift.
