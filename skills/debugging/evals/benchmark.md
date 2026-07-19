# Debugging small-model benchmark

Evaluated: 2026-07-19

Revision note: these results predate the static-analysis branch for costly or unreliable reproduction; rerun before treating them as evidence for the current skill.

Model: `gpt-5.6-terra`, the only directly selectable efficient/small model family in this runtime. Profiles: `low` and `medium` reasoning.

Method: three repository-grounded diagnosis cases, each run independently with and without `$debugging`. Agents received neither the rubric nor expected answers. A deterministic grader scored explicit evidence in the saved responses.

| Profile | With skill | Baseline | Delta |
| --- | ---: | ---: | ---: |
| low | 30/30 | 29/30 | +1 |
| medium | 30/30 | 30/30 | 0 |

All 12 runs passed the 8/10 per-case threshold. The only baseline miss was failure to explicitly reject nearby alternatives in the low-reasoning queued-job case.

## Finding

The skill is usable by the smaller model at both reasoning profiles: it consistently produced evidence-grounded diagnosis, causal chains, calibrated uncertainty, and diagnosis-only responses. This benchmark does not show material improvement over baseline because the repository documentation and prompts make the three causes relatively explicit.

## Limitations

- One model family and one run per case/profile/configuration; this is directional, not statistically powered.
- Regex grading measures explicit response evidence, not hidden tool-use quality.
- The cases test known repository failures and one documented historical incident; they do not stress highly ambiguous or novel failures.
- Evaluating Qwen, Gemma, Llama, or other small models requires an additional callable endpoint or runner.

## Next useful iteration

Use ambiguous fixtures with incomplete or misleading evidence, multiple plausible causes, and repeated seeds. Score fact/inference separation, falsification quality, correct refusal to overclaim, and stability across runs.
