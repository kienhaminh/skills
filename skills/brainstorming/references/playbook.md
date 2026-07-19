# Brainstorming playbook (Full depth)

Read this when the problem is tangled, high-stakes, or spans many interacting unknowns. It expands the loop in `SKILL.md` with the "why", the per-node mechanics, and one fully worked tree. The goal never changes: **a decomposition that converges to a real answer**, not a pretty tree.

## Why a tree, why Rumsfeld

A hard problem is hard because its parts are entangled and some parts are invisible to you. Two moves untangle it:

- **Decomposition** turns one impossible question into several answerable ones. But naive decomposition splits on the *obvious* axes and misses the parts you couldn't see — which are usually the ones that sink you.
- **The Rumsfeld matrix** is the fix: at each node it forces you past what you already know into what you know you don't know (your branches) and what you don't know you don't know (a deliberate probe). It's a lens for *generating* branches, not a template you pour the problem into.

The classic failure of tree-thinking is a beautiful, balanced tree that never answers the original question and over-splits things that were directly answerable. Everything below is built to avoid that.

## Applying Rumsfeld at a single node

At the node you're expanding, sort what you can say about it into four buckets. Each bucket has a *different* job — this is the whole method:

| Quadrant | What it is | What you do with it |
|---|---|---|
| **Known knowns** | Facts/constraints you're sure of for this node | State them as grounding. They bound the node; they are **not** branches. |
| **Known unknowns** | Things you know you'd need to figure out | **These are your branches.** Each becomes a child node (and often a question to the user). |
| **Unknown knowns** | Assumptions you're leaning on without noticing | Surface each as an explicit `assumed:` line. This is the "silent assumption = bug" rule made mechanical. |
| **Unknown unknowns** | Blind spots — branches you don't yet know exist | Run **one** generative probe to expose them, then add any that appear as branches. |

Generative probes for the fourth quadrant (pick one, don't run all):
- **Pre-mortem** — "It's 6 months later and this failed. What was the cause nobody named?"
- **Inversion** — "What single fact would make this entire branch irrelevant?"
- **Absent stakeholder** — "Whose constraint / which system / what edge case isn't represented in the branches so far?"

Emit **2–4 branches**, "clear enough" not exhaustive. You will expand the best of them next and can always split again — so resist front-loading. A node with one obvious answer needs zero branches; make it a leaf.

## Ranking the frontier (best-first)

Keep a mental (or written) list of open, unexpanded nodes — the **frontier**. Expand next the node that maximizes:

> **leverage = uncertainty × impact-on-the-root-answer**

- **Uncertainty**: how much you *don't* know here / how wide the outcomes are.
- **Impact**: how much the root answer swings on how this node resolves.

High-uncertainty but low-impact → note it and prune. Low-uncertainty high-impact → it's near-settled; state it and move on. The nodes worth digging are high×high. Naming the two factors gives you a cheap, explicit priority signal instead of expanding whatever's visually next.

Prune out loud: "Not expanding `C` — low impact on the answer." A pruned branch is a recorded decision, not an oversight.

## Stop rules (when a node becomes a leaf)

Stop expanding and answer the node directly when **any** hold:
- It's directly answerable or actionable as stated.
- Splitting it further wouldn't change the decision at the root.
- It's out of scope for the question the user actually asked.
- You're recursing for symmetry, not information — the tell is branches that just rephrase the parent.

Unbounded recursion is the enemy. When in doubt, answer the node; you can re-open it if the answer turns out to hinge on something deeper.

## Synthesis — the step people skip

Once the leaves under a subtree are answered, roll them **up**: what does `B`'s answer become, given `B1`, `B2`? Then what does `A` become, given `B, C, D`? The final output is:

1. **Answer to `A`** — direct, in the user's terms.
2. **What it rests on** — the load-bearing `known knowns` and `assumed:` lines. If one is wrong, the answer moves.
3. **What would change it** — the highest-leverage unknown still open, and how to resolve it.

If you cannot state (1), the brainstorm isn't done — either a leaf is unanswered or a pivotal unknown needs a question to the user.

## Checkpointing the user

Don't interrogate every node. Ask via AskUserQuestion **only** at a pivotal unknown — one whose resolution swings the root answer and which you genuinely can't settle yourself. Carry 2–4 concrete options, one **(Recommended)**. Everywhere else, state an `assumed:` line and keep moving; the user can point at any node id to correct you. In a non-interactive run, replace every checkpoint with your best assumption, marked `assumed:`.

## Worked example (compressed)

**Ask:** "Our onboarding conversion is dropping. What do we do?"

```
A — Reverse the onboarding conversion drop
├─ known known: drop is ~15% over 6 weeks, started ~week of the v4 signup redesign
├─ assumed: the metric definition didn't change (VERIFY — pivotal)
├─ B — Is it real, or measurement? [uncertainty hi × impact hi → expand first]
│  ├─ B1 — analytics/instrumentation changed at v4?  → leaf: event rename dropped 4% of "activated" fires. PARTLY MEASUREMENT.
│  └─ B2 — segment mix shifted (new paid channel)?   → leaf: yes, a cheap channel added low-intent traffic. REAL for that segment.
├─ C — If real, where in the funnel? [expand second]
│  ├─ C1 — step-by-step drop-off               → leaf: cliff at the new email-verify step added in v4.
│  └─ C2 — device/browser skew                 → leaf: none. prune deeper.
└─ D — Cost of acting vs waiting  [uncertainty lo × impact hi → state, don't expand]
   └─ leaf: verify-step friction is cheap to A/B; low risk to test now.

Synthesis →
Answer to A: The "drop" is ~1/3 instrumentation artifact (B1) and ~2/3 real — concentrated in
(a) the low-intent paid channel (B2) and (b) a hard drop-off at v4's new email-verify step (C1).
Act: fix the renamed event to de-noise the metric; A/B removing/deferring email-verify (D says cheap);
re-baseline the paid channel separately.
Rests on: assumed metric-def unchanged (must verify), and that C1's cliff is causal not correlational.
Would change it: if the metric definition DID change at v4, more of the drop is artifact — resolve first.
```

Note what the tree did *not* do: it didn't split `D` into subbranches (low uncertainty), didn't go deeper on `C2` (pruned), and reached a concrete action. That restraint is the skill.
