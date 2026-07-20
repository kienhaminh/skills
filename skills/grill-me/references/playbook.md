# Playbook — full-depth guidance per step

Read this when running Full mode. Light mode needs only SKILL.md + `template.md`.

## 1. Grill

The prompt never covers what the user didn't think to say. Skim the touched files
(~2 min, no deep reading), then sort the ask into the Rumsfeld matrix:

- **Known knowns** — stated, confirmable in code → don't ask; verify in Ground.
- **Known unknowns** — questions the user voiced → ask directly.
- **Unknown knowns** — context the user has but didn't say (taste, constraints,
  history) → force out with concrete either/or options; a wrong-but-specific option
  surfaces truth faster than an open question.
- **Unknown unknowns** — off the user's radar; **your main job**. Mine the code:
  adjacent features, edge cases (locale, auth, empty/error states), second-order
  effects. Design-changing ones become questions; the rest go to pre-mortems or
  Expansions parked — never silently dropped.

Use one user-input round of three or four questions; use a second round only when answers contradict.
Aim each question with a named technique:

- **5 Whys** — the goal behind the ask: what becomes possible once this is done?
- **MoSCoW** — must / should / won't for this iteration; Won't blocks scope creep.
- **Constraints** — performance, deadline, compatibility, and the repository's declared scope cap.
- **Done test** — one observable behavior proving it works.

Options do half the grilling: give two to four concrete repository-grounded answers per question and
mark one **(Recommended)**. Use checkout evidence for questions the codebase can answer.

## 2. Ground

**Source-state check first** — research built on the wrong source is worse than none. In the wrong
Git checkout, every citation looks precise and every one misleads.

1. *Where am I* — `git rev-parse --show-toplevel && git branch --show-current`;
   detached HEAD or unexpected path → find out why before reading code.
2. *Am I current* — `git log --oneline -1` vs the tip the user works on (their main
   checkout, or the branch they named).
3. *Default-branch trap* — worktrees, clones, and CI checkouts are usually created
   from the default branch; if it diverges from the working branch, confirm which
   one the task means. On a disposable copy, move to the intended ref and say so —
   never touch the user's own checkout.
4. *Dirty state* — `git status --short`; uncommitted changes ARE current reality.

In the user's own interactive Git checkout, always perform checks 1 and 4; compare tips when the user
named a branch, upstream, or other freshness target. For a non-Git source, record the absolute root
plus the strongest available provenance marker—package version, archive digest, generated manifest,
release tag, or file timestamps—and state that branch/upstream freshness cannot be proved. Then:

- Read the repository's trust order and known-debt owner when present. Treat recorded debt as context,
  not surprise scope.
- Cite every current-state claim with `file:line` or command output.
- **Premise check.** Verify in code that the problem behaves as the user says; a
  wrong premise often yields the sharpest direction (e.g. a "semantic or fuzzy
  search?" ask dissolved once code showed search was already hybrid — the real bug
  was accent folding).

## 3. Branch

3–5 directions, each from a distinct lens — five variants of one idea is a failed
branch:

- **Minimal / YAGNI** — smallest change passing the Done test.
- **First principles** — ignore current structure; design from scratch, map back.
- **Extension** — solves the ask *and* unlocks named adjacent asks.
- **Inversion** — make the problem disappear instead of solving it.
- **Reuse / buy** — existing dependency, repo pattern, off-the-shelf piece.

## 4. Kill

- **Pre-mortem** each direction: "3 months later this failed — why?" One sentence.
  Forcing a death-cause beats asking "is this good?".
- Score against the Grill answers: goal fit, scope-cap fit, effort.
- Keep 2–3 — fewer means you didn't diverge, more means you didn't kill.
- Present a short comparison table + **one** recommendation; the user picks.

## 5. Write

Follow `template.md` exactly. Notes that earn their keep:

- **Blast radius:** trace every consumer of what you touch — callers, shared
  schema/contracts, background jobs, tool/API surfaces, UI, test harnesses
  (e.g. TRUNCATE lists in integration setups). Claiming "nothing else uses this"
  requires the grep/search command as evidence.
- **FMEA-lite:** Likelihood × Impact (H/M/L). Treatment is one of
  mitigate / accept / avoid / transfer plus the concrete action — an accept needs a
  written reason, not laziness. Detection is its own column: which test, log, or
  behavior tells you it broke. H×H ⇒ change the design, not the wording.
- Rejected directions and parked expansions stay in the file — one line now beats a
  future session re-excavating the same idea.
