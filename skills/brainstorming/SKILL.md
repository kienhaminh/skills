---
name: brainstorming
description: Decompose an ambiguous, high-stakes, or multi-variable problem into a labelled problem tree, solve its leaves, and synthesize one answer. Use for open-ended life, business, product, strategy, or root-cause questions, including requests to brainstorm, phân rã, mổ xẻ, or tư duy có cấu trúc. Not for a concrete code-feature plan (use $grill-me) or a specific code failure (use $debugging).
---

# Brainstorming — recursive problem-tree

Pipeline: **Root → Expand (best-first, Rumsfeld per node) → Solve → Synthesize**. Output = a labelled markdown tree that ends in an actual answer to the root. The tree is scaffolding; the answer is the product.

## Calibrate first

Depth ∝ ambiguity × stakes × how reversible the decision is. Judge, don't ritual:

- **Light** — one clear question, few unknowns: root + one split (2–3 branches), solve, answer. A dozen lines.
- **Full** — tangled, high-stakes, many interacting unknowns: expand several levels best-first, checkpoint the pivotal unknowns with the user, solve leaves, synthesize. Read `references/playbook.md` first.

Don't over-split. A node that is directly answerable is a **leaf** — answer it, don't decompose it for symmetry.

## The loop

1. **Root (A).** Write the problem as one sharp sentence, label it `A`. If the ask is vague, sharpen it first — a fuzzy root grows a fuzzy tree.

2. **Expand a node** by applying the **Rumsfeld matrix** *as a lens to generate branches* (the four quadrants are NOT the four branches):
   - **Known knowns** → assert as grounding: settled facts/constraints for this node. Not a branch.
   - **Known unknowns** → these become the child branches (and the questions worth asking). This is the engine — decomposition is mostly "what don't we know yet that we could."
   - **Unknown knowns** → tacit assumptions you're leaning on. Surface each as an explicit stated assumption — a silent assumption is a bug.
   - **Unknown unknowns** → run one generative probe to find branches you'd have missed: **pre-mortem** ("6 months on this failed — why?"), **inversion** ("what would make this whole branch irrelevant?"), or "who/what haven't we considered?".

   Emit **2–4 branches** per split — "clear enough", not exhaustive. Over-branching early is the failure mode the user pre-flagged.

3. **Rank the frontier, descend best-first.** Score each open node by **uncertainty × impact-on-the-root-answer**. Expand the highest-leverage node next; ignore low-leverage ones (say so — a pruned branch is a decision, not an oversight). This is why you don't need every branch up front.

4. **Stop expanding a node** when any holds: it's directly answerable/actionable · splitting it further won't change the decision · it's out of scope. Then it's a leaf.

5. **Solve the leaves.** Give each leaf a concrete answer/finding/decision, with evidence where a claim is checkable.

6. **Synthesize up to A.** Roll leaf answers back through their parents into **one answer to the root question**, plus the key assumptions it rests on and what would change it. A tree with no answer at the top is unfinished.

## Node-ID scheme

Stable, referenceable labels. Root is `A`; A's children are the next capitals `B, C, D…`; every deeper split appends the child's index to the parent (add a hyphen once the id already ends in a digit):

```
A  ─┬─ B  ─┬─ B1 ─┬─ B1-1
    │      │      └─ B1-2
    ├─ C   └─ B2
    └─ D
```

Render the tree as a nested markdown list with each node's id, a one-line label, and — for leaves — its answer. Update and re-show the tree as it grows so the user can point at `B1-2` and steer.

## Rules

- **Converge.** The deliverable is the answer to `A`, not the tree. If you're drawing branches and not closing in on an answer, stop and synthesize what you have.
- **Uncertain → ask (with options) or state the assumption in the tree.** At a pivotal unknown, ask via AskUserQuestion with 2–4 concrete options, one **(Recommended)**; don't interrogate every node.
- Chat in the user's language. Keep node labels terse.
- Non-interactive run: pick the best assumption at each pivotal unknown, mark it `assumed:` in the tree, and proceed.
- Save the tree to a file only if the user asks or the problem is large enough to outlive the chat.
