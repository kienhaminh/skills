# Skill benchmark: worktree

Date: 2026-07-19. Iteration 4 used three fresh independent `with_skill` agents and the original three independent baseline agents over the same read-only, repository-grounded scenarios. Agents did not receive expected answers or the rubric.

## Result

| Case | With skill | Baseline | Delta |
| --- | ---: | ---: | ---: |
| Parallel feature development | 10/10 pass | 7/10 fail | +3 |
| Parallel integration and ingestion debugging | 10/10 pass | 9/10 pass | +1 |
| Safe cleanup and handoff | 10/10 pass | 8/10 pass | +2 |
| **Total** | **30/30; 3/3 pass** | **24/30; 2/3 pass** | **+6** |

Pass threshold: 8/10 per case.

## Token-efficiency result

| Artifact | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| `SKILL.md` words | 872 | 680 | 22.0% |
| `SKILL.md` bytes | 6,192 | 4,915 | 20.6% |
| Three with-skill response words | 6,035 | 2,781 | 53.9% |
| Three with-skill response bytes | 50,913 | 24,140 | 52.6% |

The main gain came from a 1,000-word default budget, parameterized command templates, one resource matrix, file-backed logs, a fixed handoff row, and at most three findings. The safety footer restored details that compact answers had omitted: database topology, distinct `_test` databases, exact process ownership, prune dry-run, and an explicit no-mutation statement.

## Iteration notes

- Iteration 2 reduced output but scored 23/30 because its compact contract omitted several explicit gates.
- Iteration 3 reduced output to 2,906 words and reached 29/30 after semantic-equivalence corrections; cleanup still omitted process ownership.
- Iteration 4 added a short safety footer, produced 2,781 words, and restored 30/30.
- The grader was broadened only for valid equivalent wording and multiline commands. Prompts, point weights, pass threshold, and baseline raw responses stayed unchanged.

## Artifacts

- `evals.json`: prompts and 10-point rubrics.
- `grade.py`: deterministic grader.
- `results.json`: final scores, efficiency metrics, adjustments, and limitations.
- `runs/`: final three with-skill responses and original three baseline responses.

This benchmark is directional and uses words/bytes as a transparent token proxy. It measures explicit coverage in plans; it does not execute those plans or prove every proposed command succeeds.
