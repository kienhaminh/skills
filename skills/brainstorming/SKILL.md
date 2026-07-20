---
name: brainstorming
description: Solve ambiguous, high-stakes, or multi-variable questions with a labelled problem tree. Use for open-ended life, business, product, strategy, and root-cause reasoning; route concrete feature briefs to $grill-me and specific failures to $debugging.
---

# Solve a problem tree

Use **Root → Expand → Solve → Synthesize**. The tree is scaffolding; one answer to the root is the
deliverable.

## Calibrate

Scale depth with ambiguity, stakes, and irreversibility:

- **Light:** one split with two or three branches, then answer.
- **Full:** several best-first expansions with user checkpoints at pivotal unknowns. Read
  [playbook.md](references/playbook.md) before Full mode.

A directly answerable node is a leaf. Complete calibration when the root is one sharp sentence and
the selected depth can plausibly change its answer.

## Run the loop

1. **Root (`A`).** State the exact question, decision, scope, and known constraints.
2. **Expand.** Apply the Rumsfeld matrix as a lens:
   - known knowns ground the node;
   - known unknowns become candidate child branches;
   - unknown knowns become explicit `assumed:` statements;
   - unknown unknowns get one pre-mortem, inversion, or absent-stakeholder probe.
   Emit two to four materially different branches.
3. **Rank.** Expand the frontier by `uncertainty × impact on A`. Record low-leverage branches as
   pruned.
4. **Stop.** Make a node a leaf when it is answerable, further division cannot change `A`, or it is
   outside scope.
5. **Solve.** Give every leaf a concrete answer, finding, or decision with evidence for checkable
   claims.
6. **Synthesize.** Roll leaf answers through their parents into one direct answer to `A`, its
   load-bearing assumptions, and the fact that would most change it.

Ask the user only at a pivotal unknown that evidence cannot resolve. Use the available user-input
mechanism with two to four concrete options and one recommendation. In a non-interactive run, choose
the safest plausible assumption, mark it `assumed:`, and continue.

## Label and present

Use stable IDs: `A`; children `B`, `C`, `D`; deeper nodes `B1`, `B2`, then `B1-1`. Render a nested
Markdown list so the user can steer by ID. Keep labels terse and converse in the user's language.

The brainstorm is complete only when every open node is solved, pruned, or explicitly blocked and
the final synthesis answers `A`. Return the tree in chat; save it only when the user requests a file.
