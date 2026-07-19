# Named method routing

Use one primary plus at most two supporting canonical names. Put names before task prose; explain only a nonstandard adaptation. Acceptance evidence remains the oracle.

The validator requires `methods[0]` to match the node's first operation:

| First operation | Allowed primary method |
| --- | --- |
| `problem-framing` | Rumsfeld Matrix |
| `decomposition` | MECE |
| `analysis` | Rumsfeld Matrix; Scientific Method; FMEA; STRIDE; Bayesian Updating |
| `feature-plan` | Double Diamond |
| `story-slicing` | INVEST |
| `prototyping` | Throwaway Prototyping; Evolutionary Prototyping; Characterization Testing; Dry Run |
| `test-design` | TDD |
| `implementation` | YAGNI; TDD; Contract Testing; Walking Skeleton |
| `diagnosis` | Scientific Method |
| `integration` | Contract Testing |
| `verification` | Popperian Falsification |
| `docs-sync` | Single Source of Truth |
| `bootstrap` | Walking Skeleton |
| `worktree-management` | Trunk-Based Development |

Supporting registry: Rumsfeld Matrix, YAGNI, DRY, KISS, MoSCoW, Vertical Slicing, Wizard of Oz, Equivalence Partitioning, Boundary Value Analysis, Five Whys, Fault Tree Analysis, Consumer-Driven Contracts, FMEA, Premortem, Poka-Yoke, STRIDE, Attack Trees, Defense in Depth, Negative Testing, Metamorphic Testing, Differential Testing, Bayesian Updating, Evidence Hierarchy, Calibration, Docs as Code, and any primary name above.

Compact form:

```text
Methods: MECE -> Rumsfeld Matrix -> YAGNI.
Partition requirements; classify pivotal uncertainty; defer non-required work.
```
