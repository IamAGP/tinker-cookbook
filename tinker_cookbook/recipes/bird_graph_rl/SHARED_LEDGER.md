# Shared experiment ledger

One row per checkable fact. **Append-only**: never edit or delete a row; if a fact is superseded,
add a new row that says which one it replaces. Every agent on the project appends here; the
detailed reasoning stays in each agent's own `JOURNAL.md`. A blog sentence with a number in it
should be traceable to exactly one row.

Columns: `id` · `date` · `claim` · `evidence` (file, commit or command that reproduces it) ·
`by` (who measured) · `verified` (who reproduced it independently, or `—`).

| id | date | claim | evidence | by | verified |
|---|---|---|---|---|---|
| F01 | 2026-09-20 | Graph: 649,846 nodes, 1,380,394 relationships; every label and relationship type equals the source row counts | JOURNAL "E0 results"; export manifest | tinker | — |
| F02 | 2026-09-21 | 186 evaluation questions (BIRD corrected dev release, `codebase_community`): 151 simple / 30 moderate / 5 challenging; all gold SQL executes, 0 errors, 0 empty | JOURNAL "E1 results" | tinker | — |
| F03 | 2026-09-21 | The older mini-dev gold SQL gives a different executed answer on 8 of the 49 overlapping questions | JOURNAL "E1 results" | tinker | — |
| F04 | 2026-09-21 | The 186 questions cover 64 distinct query structures (42 appear once); no query touches more than 3 tables; 90 use no aggregation | JOURNAL "how much structure" | tinker | — |
| F05 | 2026-09-21 | Zero-shot Qwen/Qwen3.8-27B on Tinker: strict 0.608, lenient 0.677 (simple .675, moderate .367, challenging 0/5); 1 sample, T=1.0, ≤8 turns | `~/bird_rl_runs/e2_full_qwen3_8_27b/summary.json`; harness blob 6390bc9 | tinker | fireworks |
| F06 | 2026-09-22 | Same harness on Fireworks, same checkpoint: strict 0.608, lenient 0.656 | `~/bird_rl_runs/e2fw_full_qwen3_8_27b/summary.json` | fireworks | tinker |
| F07 | 2026-09-22 | Paired across the two runs: both right 92, both wrong 52, 21 flips each way; McNemar exact p = 1.00; agreement 0.774 → no framework effect, and 22.6% of questions flip between two single samples | recomputed from both `results.jsonl` | fireworks | tinker |
| F08 | 2026-09-22 | 134 of 186 questions are solved in at least one of the two samples | same files | tinker | — |
| F09 | 2026-09-22 | Cost of one 186-question pass on the 27B: $2.33 on Tinker (console balance), $3.12 on Fireworks (billing, 47% of prompt tokens cached) | console screenshots; Fireworks billing | owner / fireworks | — |
| F10 | 2026-09-22 | Of the 73 failures in F05: 0 had no runnable final query; 8.1% of tool calls errored mid-rollout | `results.jsonl` | tinker | — |
| F11 | 2026-10-03 | Partial-credit reward (row-level F1, exact references): mean 0.640 / 0.643 on the two runs vs 0.608 strict | `reward.py` blob e326e77; re-execution of 372 stored queries | tinker | fireworks |
| F12 | 2026-10-03 | Of the 52 never-solved questions, 13 get non-zero partial credit and 39 stay at exactly zero; questions with reward spread across the two samples: 42 (binary) → 47 (partial) | same | tinker | fireworks (same 13 ids) |
| F13 | 2026-10-03 | Re-executing stored final queries reproduces stored results: 0 rescore errors, 0 strict drift across 372 queries | Fireworks `verify_partial_credit.py` | fireworks | — |
| F14 | 2026-10-03 | Rendered prompt tokens for Qwen3.8-27B are byte-identical under transformers 4.57.6 and 5.10.4 (82 tokens, sha e566e17f006d7e12), one conversation tested | JOURNAL | tinker | — |
| F15 | 2026-10-03 | Release dates from providers' own sources: Qwen3.8-27B 2026-08-14; GLM-5.3 2026-08; DeepSeek-V3.1 2025-08-21 | JOURNAL "research … near the frontier" (URLs in sub-agent report) | tinker (sub-agent) | — |
| F16 | 2026-10-03 | `perplexity-ai/pplx-decider-v1-27b`: 48.59 GiB BF16, 255-way linear head, no `lm_head`, not servable by vLLM, input cap 8,192 tokens in shipped code | JOURNAL "research … self-hosted" | tinker (sub-agent) | fireworks (existence, size, licence) |
| F17 | 2026-10-03 | Supersedes the Fireworks half of F09: $3.12 is the bill for 197 rollouts (1 probe + 10 smoke + 186 full), not one pass. Billed tokens equal the harness meter exactly (1,577,817 prompt of which 743,000 cached; 231,187 completion) and list prices reproduce $3.12. One 186-question pass pro-rates to about $2.98 (estimate: billing cannot split the runs) | `firectl billing get-usage --start-time 2026-09-21 --end-time 2026-09-23 --group-by model_name`; Fireworks JOURNAL "E2-FW full run" | fireworks | — |
| F18 | 2026-10-03 | Fireworks serverless-training prices for Qwen3.8-27B per M tokens: prefill 1.86, cached 0.372, sample 5.595, train 4.103; identical to Tinker's prefill/cached/sample for the same model | Fireworks docs `/fine-tuning/cost-estimator` catalog (generated 2026-09-30); F17 reproduces the first three from a real bill | fireworks | — |
| F19 | 2026-10-03 | Qwen3.5-9B on Fireworks: LoRA-tunable for SFT and RL, but NOT on serverless training (catalog `serverless: null`; changelog deprecation effective 2026-08-26). Only dedicated shapes exist: `qwen3p5-9b-65k-lora`, `-256k-lora`, `-256k`, each 2 × B200 | `firectl model get`, `firectl training-shape list -a fireworks`; docs `/updates/changelog`, `/fine-tuning/cost-estimator` | fireworks | — |
| F20 | 2026-10-03 | Qwen3.5-4B on Fireworks is not trainable: registry entry is READY but carries no LoRA flag and no tunable flags, has no training shape, and is absent from the cost catalog | `firectl model get accounts/fireworks/models/qwen3p5-4b -o json`; `firectl training-shape list`; docs cost catalog | fireworks | — |
| F21 | 2026-10-03 | Fireworks dedicated GPU rates per GPU-hour (effective 2026-09-01): H100 $8, H200 $8, B200 $13, B300 $15, GB300 $20. RL on Qwen3.5-9B needs a 2 × B200 trainer plus a 1 × B200 BF16 sampler deployment (`rft-qwen3p5-9b-v2`), so $39 per hour while both are up, idle and provisioning included | docs cost catalog `gpuRates`; `firectl deployment-shape-version get …/rft-qwen3p5-9b-v2/versions/gcr1owmp` | fireworks | — |
| F22 | 2026-10-03 | 172 of the 186 evaluation questions carry a non-empty hint (BIRD `evidence`), median 68 characters; the harness appends it to the user turn | `load_references` on `reference_answers.json`, harness `question_text` | fireworks | — |
| F23 | 2026-09-22 | Sampling parity between platforms was checked in source, not assumed: the Fireworks SDK forces `top_k=0`, `top_p=1.0` (tinker defaults `top_k=-1`, `top_p=1`); the renderer's stop id 248046 `<|im_end|>` is returned in the completion tokens; sampling logprobs align one-to-one with tokens | SDK `fireworks/training/sdk/sampling.py`; Fireworks JOURNAL "E2-FW probe" | fireworks | — |
| F24 | 2026-10-03 | Fireworks custom-model upload expects standard Hugging Face files for a supported generation architecture; the docs describe no mechanism for a separate read-out head, so the decider in F16 is not deployable there as documented | docs `/models/uploading-custom-models` | fireworks | — |
| F25 | 2026-10-03 | Zero-shot Qwen/Qwen3.5-9B on Tinker, same harness and 186 questions: strict 0.425, lenient 0.591 (simple .483, moderate .167, challenging 1/5); renderer `qwen3_5`, 1 sample, T=1.0 | `~/bird_rl_runs/e3_qwen3_5_9b/summary.json` | tinker | — |
| F26 | 2026-10-03 | Zero-shot Qwen/Qwen3.5-4B, same: strict 0.376, lenient 0.489 (simple .430, moderate .167, challenging 0/5) | `~/bird_rl_runs/e3_qwen3_5_4b/summary.json` | tinker | — |
| F27 | 2026-10-03 | Gap to the Qwen3.8-27B reference (0.608 strict, F05): 18.3 points for the 9B, 23.2 points for the 4B; single-sample figures, so each carries roughly ±3.6 points | F05, F25, F26 | tinker | — |
