# Complex static-debugging benchmark

Evaluated: 2026-07-19

Model: `gpt-5.6-terra`; reasoning profiles: `low`, `medium`.

Method: three isolated, expensive-to-reproduce fixtures (lost update, retry after an external side effect, and cross-tenant cache collision). Natural prompts did not encode the workflow. Runs were blind, read-only, and independently graded for diagnosis quality plus a 200-word output limit.

## Current compact skill

| Profile | With skill | Baseline | Delta | With-skill pass | Baseline pass |
| --- | ---: | ---: | ---: | ---: | ---: |
| low | 30/30 | 26/30 | +4 | 3/3 | 2/3 |
| medium | 30/30 | 26/30 | +4 | 3/3 | 2/3 |

All skill-guided runs stated the causal chain, confidence boundary, violated invariant, rejected alternative, and remaining confirmation evidence. All stayed below 200 words.

| Profile | With-skill average | Baseline average | Difference |
| --- | ---: | ---: | ---: |
| low | 164 words | 162 words | +1% |
| medium | 167 words | 172 words | -3% |

The skill itself fell from 438 to 215 words (-51%) while quality remained 30/30.

## Interpretation

The compact skill improves explicit diagnostic discipline without materially increasing output length. It still adds about 215 input words whenever triggered, so it does not guarantee fewer total tokens than no skill. Its token benefit is relative to the previous 438-word skill and from preventing verbose process narration.

## Limitations

- One model family and one run per case/profile/configuration.
- Word count is an output-token proxy; exact input/output token usage was unavailable.
- Regex grading checks explicit evidence, not hidden reasoning quality.

## Reproducible artifacts

- `evals.json`: prompts, model profiles, checks, and pass threshold.
- `fixtures/`: isolated repository evidence for each diagnosis case.
- `../grade.py`: deterministic grader; defaults to this suite.
- `runs/`: one sanitized final baseline/with-skill response per case and profile.
- `results.json`: grader output regenerated from `runs/`.

Keep ad-hoc or replacement runs under the repository's ignored `.local-evals/` directory. Promote a
new `runs/` set only when the benchmark summary is intentionally refreshed.
