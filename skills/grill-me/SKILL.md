---
name: grill-me
description: Turn a rough initial request into vetted solution directions and an implementation write-up grounded in the current codebase. Use whenever the user pitches a feature idea, says "grill me", asks to brainstorm/mở rộng/explore options, or gives a vague requirement that needs sharpening before any coding — even if they never say "brainstorm". Not for bug fixes or tasks with one obvious implementation.
---

# Grill Me

Pipeline: **Grill → Ground → Branch → Kill → Write**. Output = one markdown file. No code, no commits.

## Calibrate first

Depth ∝ ambiguity × blast radius × irreversibility. Judge, don't ritual:

- **Light** — clear ask, 1–2 files, reversible: 0–2 questions, 2–3 directions, risks as a short paragraph.
- **Full** — vague ask, cross-module, schema/contracts, hard to undo: every step at full depth; read `references/playbook.md` first.

Invariants at any depth (cheap, and they catch the expensive failures): repo-state check, `file:line` evidence, uncertain → ask or warn.

## Steps

1. **Grill** — skim touched files, sort the ask into a **Rumsfeld matrix**; mining unknown unknowns from code is your main job. Ask via AskUserQuestion — every question carries 2–4 repo-real options, one **(Recommended)**. Techniques: **5 Whys**, **MoSCoW**, **constraints** (MVP scope cap — `docs/PLANS.md`), **Done test**.
2. **Ground** — **repo-state check** before reading: right repo, right branch, current tip, dirty state — worktrees/clones/CI checkouts often start stale on the default branch (details in playbook). **Premise check**: the user's description of current behavior is a hypothesis. Trust `docs/README.md`; don't "fix" `docs/plans/tech-debt.md` debt. Every claim cites `file:line`; "it seems" is banned.
3. **Branch** — 3–5 directions, distinct lenses: **YAGNI**, **first principles**, **extension**, **inversion**, **reuse/buy**.
4. **Kill** — **pre-mortem** each ("3 months later it failed — why?"); score goal/scope/effort; keep 2–3; present **one** recommendation, the user picks.
5. **Write** — `docs/plans/active/<topic-kebab>.md`, English, shaped by `references/template.md`. Impact & risks = **blast radius** (evidence-backed) + **FMEA-lite** (L×I, treatment, detection; H×H ⇒ redesign).

## Rules

- **Uncertain → ask (with options) or warn in the file.** A silent assumption is a bug.
- Chat in the user's language; the file in English. Record rejected directions.
- Non-interactive run: record assumed answers, pick your own recommendation, say so.
