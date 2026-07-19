# Complex static-debugging benchmark

Evaluated: 2026-07-19

Model: `gpt-5.6-terra`; reasoning profiles: `low`, `medium`.

Method: three isolated, expensive-to-reproduce fixtures (lost update, retry after an external side effect, and cross-tenant cache collision). Natural prompts did not encode the workflow. Runs were blind, read-only, and independently graded for diagnosis quality plus a 200-word output limit.

## Compact skill (v3)

| Profile | With skill | Baseline | Delta | With-skill pass | Baseline pass |
| --- | ---: | ---: | ---: | ---: | ---: |
| low | 30/30 | 26/30 | +4 | 3/3 | 2/3 |
| medium | 30/30 | 26/30 | +4 | 3/3 | 2/3 |

All skill-guided runs stated the causal chain, confidence boundary, violated invariant, rejected alternative, and remaining confirmation evidence. All stayed below 200 words.

| Profile | With-skill average | Baseline average | Difference |
| --- | ---: | ---: | ---: |
| low | 164 words | 162 words | +1% |
| medium | 167 words | 172 words | -3% |

The skill itself fell from 438 to 215 words (-51%). Compared with v2 skill-guided outputs, observed output length fell from 357 to 164 words at low reasoning and from 235 to 167 at medium reasoning, while quality remained 30/30.

## Interpretation

The compact skill improves explicit diagnostic discipline without materially increasing output length. It still adds about 215 input words whenever triggered, so it does not guarantee fewer total tokens than no skill. Its token benefit is relative to the previous 438-word skill and from preventing verbose process narration.

## Limitations

- One model family and one run per case/profile/configuration.
- Word count is an output-token proxy; exact input/output token usage was unavailable.
- Stochastic runs make cross-version length comparisons directional, not exact.
- Regex grading checks explicit evidence, not hidden reasoning quality.
