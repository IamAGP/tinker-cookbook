# Legal RL — Experiment Journal

A running lab notebook for the legal multi-turn tool-use RL project. Entries are
append-only and chronological. Every result is traceable to a config, a commit,
and a log path so it can be reproduced. Interpretations are kept separate from
observations: **Observed** = what the numbers say; **Interpretation** = what we
think it means; **Decision** = what we changed and why.

---

## 1. Objective

Train a language model to answer legal questions by **strategically using a
retrieval tool** — deciding when to search, what to search for, when it has
enough evidence, and how to phrase a correct final answer — via reinforcement
learning with a verifiable reward.

This is *agentic* RL (multi-turn, tool-augmented), not single-turn QA. The model
already knows law from pretraining; the thing we are trying to teach is the
*policy of tool use under uncertainty*.

**Success definition (what "it worked" means):**
- Primary: correctness reward rises meaningfully above the untrained baseline on
  held-out questions.
- Secondary: the model retains/increases productive tool use
  (`turns_per_episode > 1`) rather than collapsing to a degenerate shortcut.
- Guardrail: it does not reward-hack (improve a proxy metric while the true task
  metric stays flat).

---

## 2. Fixed experimental setup

Unless an entry says otherwise, all runs use:

| Component | Choice | Rationale / notes |
|---|---|---|
| Base model | `Qwen/Qwen3-4B-Instruct-2507` | Matches the upstream `search_tool` recipe; verified present in Tinker server capabilities. |
| Fine-tuning | LoRA, rank 32 | Base weights frozen; adapters on attention/projection layers. |
| Trainer | Tinker (`importance_sampling` loss), GRPO-style | Advantages centered within group: `A_i = R_i − mean(R_group)`. |
| Renderer | `qwen3_instruct` (auto-resolved) | Resolved via `resolve_renderer_name_from_checkpoint_or_default_async`. |
| Embeddings | AWS Bedrock **Titan** `amazon.titan-embed-text-v2:0`, 1024-dim | See §6 (why not Cohere). |
| Vector DB | ChromaDB `PersistentClient`, local, HNSW + cosine | 342 chunks; no server process, no API key. |
| Retrieval corpus | `isaacus/legal-rag-qa`, `corpus` config (190 passages → 342 chunks) | Chunked ≤20k chars (see §6, token-limit bug). |
| Training questions | `isaacus/legal-rag-qa`, `qa` config (138 QA pairs) | Criminal-law textbook QA with long-form gold answers. |
| Reward | `TextAnswerReward`: `0.1·(format−1) + correct` | `format` = contains "Answer:"; `correct` = normalized exact match. **This is the current bottleneck — see Exp 1.** |
| Env limits | `max_turns=5`, `max_tokens=1024`, `max_trajectory_tokens=32k` | |

**Reproduction entry points:**
- Build index: `python -m tinker_cookbook.recipes.legal_rl.build_index`
- Baseline: `python -m tinker_cookbook.recipes.legal_rl.baseline_inference`
- Train: `python -m tinker_cookbook.recipes.legal_rl.train`
- Required env: `TINKER_API_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, and `WANDB_API_KEY` (env var required — see §6).

---

## 3. Metric definitions (so numbers are unambiguous)

| Metric | Meaning | Why we watch it |
|---|---|---|
| `env/all/reward/total` | Mean episode reward across the batch | Headline signal. |
| `env/all/correct` | Fraction of episodes with a correct answer (per reward fn) | The true task metric. |
| `env/all/format` | Fraction with "Answer:" prefix | Proxy/hygiene metric — easy to game. |
| `env/all/turns_per_episode` | Mean model turns per episode | >1 ⇒ tool was used. 1.0 ⇒ answered directly, no search. |
| `env/all/by_group/frac_mixed` | Fraction of groups with reward variance | **The learnability signal.** 0 ⇒ no advantage ⇒ no gradient. |
| `optim/entropy` | Policy entropy | Collapse toward 0 = overconfident/degenerate. |
| `optim/kl_sample_train_v1/v2` | KL between sampler and trainer logprobs | Sanity check on off-policy drift. |

---

## 4. Experiment log

### Exp 0 — Baseline: untrained base model + search tool
- **Date:** 2026-06-05
- **Question:** Before training, can the base model use the tool, and what does the
  current reward say about it?
- **Setup:** `baseline_inference.py`, `num_questions=3`, untrained
  `Qwen3-4B-Instruct-2507`, same env/tool/reward as training.

**Observed**

| Metric | Value |
|---|---|
| Mean reward | 0.000 |
| Format compliance | 1.000 |
| Correctness (exact match) | 0.000 |
| Mean turns/episode | 1.67 |

Qualitative: on the bribery question (*State v. Carr*), the model searched,
retrieved the right case, and produced an answer that was **substantively
identical** to the gold answer ("upheld … not a lesser included offense …
bribery is not a specific-intent crime"). Reward was still 0.

**Interpretation**
- The base model *already* performs the target agentic behavior (searches in
  ~⅔ of episodes) and answers correctly in substance.
- The exact-match reward scores correct long-form answers as wrong. The reward —
  not the model's capability — is the binding constraint.

**Decision**
- Proceed to one training run *as-is* anyway, to confirm the failure mode
  empirically before investing in a better reward.

---

### Exp 1 — RL training with exact-match reward
- **Date:** 2026-06-05
- **Hypothesis:** With a near-always-zero reward, GRPO will have ~no advantage
  signal and the model will not improve on correctness. (Pre-registered
  expectation: flat/degenerate.)
- **Config:** defaults from §2. `group_size=4`, `groups_per_batch=8`,
  `learning_rate=4e-5`, `format_coef=0.1`, `kl_penalty_coef=0`. 17 batches
  (138 QA ÷ 8).
- **Log path:** `/tmp/tinker-examples/legal_rl/legal-rl-Qwen-Qwen3-4B-Instruct-2507-32rank-4e-05lr-4group-2026-06-05-22-28/`
- **Final checkpoint:** `tinker://577df6ee-8f2d-5dd6-8da8-84af310ba02e:train:0/weights/final`
- **W&B:** none — logging silently skipped (see §6 WANDB_API_KEY bug).

**Observed** (start vs end)

| Metric | Step 6 | Step 16 (final) |
|---|---|---|
| `turns_per_episode` | 1.69 | **1.00** |
| `format` | 0.969 | 1.000 |
| `correct` | 0.000 | 0.000 |
| `reward/total` | −0.003 | 0.000 |
| `frac_mixed` | 0.125 | **0.000** |
| `entropy` | 0.351 | 0.499 |

Pipeline verification (iteration 5 logtree): 8 tool calls, 8 tool results, 14
queries issued, 11 documents retrieved — e.g. real text of *People v.
Silverberg*, 1 Misc.3d 62 (2003). End-to-end retrieval confirmed working.

**Interpretation**
- Correctness never left 0. The *only* reward variance came from the format
  penalty (a few episodes missing "Answer:"). `frac_mixed` → 0 by the end means
  the gradient signal vanished entirely.
- The model **regressed via reward hacking**: it drove `format` to 1.0 and
  *abandoned the search tool* (`turns_per_episode` 1.69 → 1.0). Searching costs
  tokens and risks format/context errors with zero correctness payoff, so the
  policy learned the cheapest way to capture the only available signal — answer
  directly, always prefix "Answer:".
- Net effect: training made the agent *worse* at the intended behavior than the
  untrained baseline (which at least searched). This is the canonical failure of
  optimizing a proxy when the true-task reward is flat.

**Decision**
- Do not continue with exact-match reward. Replace `TextAnswerReward` with an
  **LLM-as-judge** reward that grades semantic correctness on a graded scale
  (0.0–1.0), restoring real within-group variance → real advantages.
- Fix W&B env-var issue before the next run so training is observable live.

---

### Exp 2 — RL training with LLM-as-judge reward
- **Date:** 2026-06-06
- **Hypothesis:** A model-based reward grading semantic correctness will restore
  within-group reward variance (`frac_mixed > 0`) and eliminate the format-hacking
  collapse, because correctness — not formatting — becomes the dominant signal.
- **What changed vs Exp 1 (only the reward):**
  - New `LLMJudgeReward` (`tools.py`): a **frozen base model** (Qwen3-4B-Instruct-2507,
    no checkpoint, temperature 0) grades `(question, reference, candidate)` and
    returns CORRECT/PARTIAL/INCORRECT → 1.0/0.5/0.0. Frozen ⇒ policy cannot game
    its own judge. Reward = judge score; `format` is logged but **not** rewarded
    (to avoid Exp 1's hacking). Verdict parser checks "INCORRECT" before "CORRECT"
    (substring trap) and falls back to 0.0 on unparseable replies.
  - Wired via `reward_type="judge"` (default) through `legal_env.py` / `train.py`.
  - W&B env-var fixed → live logging confirmed.
- **Config:** identical to Exp 1 otherwise. `group_size=4`, `groups_per_batch=8`,
  `lr=4e-5`, `kl_penalty_coef=0`, 17 batches. Judge max_tokens=64.
- **Log path:** `/tmp/tinker-examples/legal_rl/legal-rl-Qwen-Qwen3-4B-Instruct-2507-32rank-4e-05lr-4group-2026-06-06-11-04/`
- **Final checkpoint:** `tinker://ef4946b1-b0cd-5e34-a0dd-9d9b1d62e817:train:0/weights/final`
- **W&B:** https://wandb.ai/giridharanadithya-itsme/legal-rl/runs/hut1ryl6

**Observed** (final step 16, vs Exp 1 final)

| Metric | Exp 1 (exact) | Exp 2 (judge) |
|---|---|---|
| `correct` | 0.000 | 0.688 |
| `judge_score` | — | 0.750 |
| `reward/total` | 0.000 | 0.750 |
| `frac_mixed` | 0.000 | 0.625 |
| `frac_all_good` / `frac_all_bad` | — | 0.250 / 0.125 |
| `turns_per_episode` | 1.00 | 1.69 |
| `format` | 1.000 | 0.969 |
| `entropy` | 0.499 | 0.417 |

W&B trend for `correct` across 17 steps: `▂▃▆▃▃▄▇▄▁▄▄█▅▄▃▅█` — noisy, ends high,
**not** a clean monotonic curve. `judge_score` mean (0.75) > binary `correct`
(0.69) ⇒ the judge issues PARTIAL/INCORRECT verdicts too (not rubber-stamping).

**Interpretation**
- *Confirmed (reward mechanism):* the judge restores a learnable signal —
  `frac_mixed` 0.0 → 0.625, and the policy retained tool use (`turns` stayed 1.69,
  no hacking collapse). Both Exp 1 failure modes are gone. This validates the
  reward redesign.
- *NOT established (policy learning):* `correct=0.69` is on **training** questions
  graded by the judge, on a *different question subset each batch*. We cannot
  separate "policy improved" from "later batches were easier." The noisy,
  non-monotonic trend is consistent with variance, not demonstrated learning.
  No held-out eval exists yet.
- *Retrieval relevance is suspect:* in an observed transcript, the question
  concerned *In re V.V.C.* (arson / incorporated-city-limits element) but the
  retrieved passage was about substantive due process (*Bowers*/*Lawrence*) —
  unrelated. The model answered correctly anyway from parametric knowledge. If
  the model is right despite irrelevant retrieval, the reward may be reinforcing
  answer phrasing rather than better search behavior.

**Decision**
- Keep the judge reward as the default. Treat Exp 2 as a successful
  *reward-mechanism* result, **not** evidence of a better agent.
- Before claiming any learning, build a **frozen held-out eval split** and measure
  untrained-base vs Exp 2-checkpoint on unseen questions (Exp 3).
- Separately investigate retrieval relevance: is the search tool actually helping,
  or is the model answering from pretrained knowledge regardless of retrieved text?

---

### A1 — Retrieval audit (analysis, not a training run)
- **Date:** 2026-06-06
- **Hypothesis under test:** "The RAG retriever is broken" — raised in Exp 2's
  interpretation after observing ONE transcript (*In re V.V.C.*) where retrieval
  returned an unrelated passage. Pre-registered as a hypothesis to be tested, not
  assumed.
- **Method:** `retrieval_audit.py`. For all 138 QA pairs, embed the **literal
  question** with the same Titan + ChromaDB stack the agent uses, retrieve top-k,
  map each retrieved chunk back to its source passage id (`metadata["id"]`), and
  check against the `relevant_passages` ground truth. Using the literal question
  isolates the *retriever* from the agent's query-formulation. Precondition
  verified first: all 138 questions (218 passage refs) have their gold passage
  present in the index — so any miss is a retrieval-quality miss, not missing data.

**Observed**

| Metric | Value |
|---|---|
| recall@1 | 0.710 |
| recall@3 (agent uses `n_results=3`) | **0.775** |
| recall@5 | 0.804 |
| recall@10 | 0.877 |
| MRR | 0.752 |
| hard misses (not in top-10) | 17/138 (12%) |

**Interpretation**
- **Hypothesis REFUTED.** The retriever surfaces the gold passage into the top-3
  for ~78% of questions — solid, not broken. The single V.V.C. anecdote that
  motivated the hypothesis was either a tail miss (12% never appear even in top-10)
  or, more likely, the agent generated a worse query than the literal question.
- A clean methodological lesson recorded: a one-transcript observation is an
  anecdote, not a finding; the 138-question audit overturned it.
- **Scope caveat:** this tested the retriever with the *literal question*. The
  agent's *self-generated queries* are a separate, still-untested variable.

**Decision / updated suspicion map**
- Ruled out: index/embeddings/chunking quality; ground-truth coverage.
- Still open: (a) agent query quality vs literal-question quality; (b) grounding —
  does the answer depend on retrieved text or on parametric memory.
- Re-prioritize: **held-out eval (Exp 3) is now the top next step** — the
  retriever is validated, so measuring real before/after learning is the highest-
  value move.

---

### A2 — Re-index with small chunks (infra change before Exp 3)
- **Date:** 2026-06-06
- **Why:** `evaluate.py` crashed with context overflow (35,411 prompt tokens >
  32,768 window). Root cause: 20k-char chunks → ~5k tokens each → `n_results=3`
  ≈ 15k tokens of retrieved text per turn, which overflows over multi-turn
  episodes. The 20k cap was an *embedding-limit* convenience, not a *retrieval*
  choice.
- **Change:** `MAX_CHARS` 20,000 → 1,500 (~375 tokens/chunk). Index rebuilt:
  342 → **3,557 chunks**.
- **Verified (re-ran retrieval audit):** recall@3 = **0.775 — unchanged** (the k
  the agent actually uses). recall@1 0.710→0.688, recall@10 0.877→0.826 (drop is
  benign: with small chunks the top-10 fills with duplicate chunks of the same
  2–3 passages). Context per search cut ~15k → ~1.1k tokens; overflow fixed.
- **Decision:** keep small chunks. Same operational retrieval, far less context
  bloat, no overflow. Don't change the model just to mask overflow (rejected the
  "bigger context window" route as a confound + cost for no retrieval-precision
  gain).

---

### Exp 3 — Held-out evaluation: does outcome-judge RL actually improve the agent?
- **Date:** 2026-06-06
- **Hypothesis:** If Exp 2's training-reward rise (`correct` 0→0.69) reflects real
  learning, the trained checkpoint should beat the untrained base on a frozen
  held-out set never seen in training.
- **Method:** Deterministic 110/28 train/eval split (`SPLIT_SEED=12345`, fixed,
  independent of training seed; verified zero overlap). **Retrained on the 110
  train split only** (`split_role=train`, judge reward, default hyperparams, 13
  batches) so the 28 eval are genuinely unseen. Evaluated untrained base vs the
  trained checkpoint on the **same 28** with the same frozen judge (`evaluate.py`).
- **Train run log:** `/Users/adithyagiridharan/Desktop/legal_rl_runs/exp3/`
  (persistent, not /tmp). Checkpoint:
  `tinker://54e51bd9-80e1-5299-8937-2d217a5374be:train:0/sampler_weights/final`.
- **Note:** sampling requires the `sampler_weights/...` path, not `weights/...`.

**Observed (held-out, 28 Q)**

| Metric | Base (before) | Trained (after) | Δ |
|---|---|---|---|
| correctness | 0.500 | 0.500 | 0.000 |
| judge_score | 0.571 | 0.554 | −0.017 |
| format | 0.929 | 1.000 | +0.071 |
| turns/episode | 1.61 | 2.29 | +0.68 |

Training-reward trend (on train split) was healthy and non-collapsing
(~0.25–0.69, turns held ~2) — i.e. the run "worked" by training-reward, yet did
not generalize.

**Interpretation**
- **No detectable improvement on held-out.** Correctness flat at 0.50;
  judge_score change (−0.017) is within noise. With n=28, SE on a 0.5 rate ≈
  0.094, so any |Δ| < ~0.1 is noise → the honest claim is "no learning detected,"
  not "got worse."
- **Exp 2's 0.69 was an illusion of the metric**, not learning: it was measured
  on *training* questions over shifting batches. The held-out eval — built
  precisely to catch this — caught it.
- What training *did* change: surface behaviors (always-format 0.93→1.0; more
  searching 1.61→2.29 turns), not correctness.
- **Likely causes** (consistent with prior findings): (1) base 4B already near
  ceiling on this memorizable, published-case dataset; (2) outcome reward +
  memorizable data ⇒ weak pressure on the real skill; (3) small training (110 Q,
  13 batches).

**Decision**
- Do not claim the legal agent was improved by RL. Exp 3 is a clean **negative
  result** and the most important finding so far: the held-out protocol is now
  the gate every future run must pass.
- The negative result empirically justifies the parked ideas: a **retrieval-
  necessary dataset** (so the tool is required, not optional) and/or a
  **trajectory/grounding reward**. On a memorizable dataset there is little the
  agent can learn that it doesn't already know.
- *(Superseded by A3 below — the grounding probe overturned the "memorizable
  dataset" explanation.)*

---

### A3 — Grounding probe: does the model actually use retrieval?
- **Date:** 2026-06-06
- **Hypothesis under test:** "The dataset is memorizable; the model answers from
  parametric memory, not the tool" — the leading explanation for Exp 3's null
  result. Tested directly, not assumed.
- **Method:** `evaluate.py disable_retrieval=True`. Tool stays present (agent
  still calls it) but returns "No relevant documents found." Compare base-model
  held-out correctness with retrieval ON vs OFF, same 28 questions.

**Observed (base model, held-out 28 Q)**

| | retrieval ON | retrieval OFF | Δ |
|---|---|---|---|
| correctness | 0.500 | 0.286 | −0.214 |
| judge_score | 0.571 | 0.375 | −0.196 |

**Interpretation**
- **Hypothesis REFUTED.** Removing retrieval drops correctness 43% (0.50→0.29).
  The model genuinely uses the tool; it is *not* answering from memory. (n=28:
  the 0.214 gap ≈ 2.3 SE — reasonably solid.)
- This reframes Exp 3. The three numbers: base+retrieval 0.50, trained+retrieval
  0.50, base−retrieval 0.29. Retrieval lifts the base 0.29→0.50, but the **base
  already captures that full benefit untrained**, and RL couldn't push past 0.50.
- New leading explanation for Exp 3's flatness: **0.50 looks like a competence
  ceiling for the 4B** on these hard legal questions — remaining errors are
  likely *reasoning* limits, which tool-use RL can't fix — not a memorizable
  dataset.

**Decision / revised priorities**
- Demote "retrieval-necessary dataset": the dataset already rewards retrieval.
- New top question: **is 0.50 a 4B capacity ceiling?** Cheap test first —
  *inference-only* eval of a bigger base model on the same 28 held-out (no
  training). If it scores meaningfully higher with the same retrieval → capacity
  is the constraint and RL on a bigger model has headroom (→ Exp 4). If it also
  plateaus near 0.50 → the ceiling is the task/eval, and we rethink.

---

### A4 — Capacity probe: bigger base model, inference only
- **Date:** 2026-06-06
- **Method:** `evaluate.py base_model=Qwen/Qwen3-30B-A3B-Instruct-2507` (same
  family/version as the 4B, MoE so ~3B active = cheap), no training, retrieval on,
  same 28 held-out.

**Observed (base, held-out 28 Q)**

| | 4B | 30B-A3B |
|---|---|---|
| correctness | 0.500 | 0.643 |
| judge_score | 0.571 | 0.750 |
| turns | 1.61 | 2.64 |

**Interpretation:** the 30B base beats the 4B base (+0.14 correctness, untrained)
→ 0.50 was partly a **4B capacity ceiling**, not a task ceiling. Headroom exists.
(n=28, +0.14 ≈ 1.5 SE — suggestive.) Notable: the 30B *base* (0.64) already beats
the 4B *after RL* (0.50). Justifies Exp 4 (RL on the 30B).

---

### Exp 4 — RL on the 30B (does training add on top of the bigger base?)
- **Date:** 2026-06-06
- **Hypothesis:** With the capacity ceiling removed, RL should push the 30B's 0.64
  base higher on held-out.
- **Method:** identical to Exp 3 except `model_name=Qwen3-30B-A3B-Instruct-2507`.
  Train on 110 train split, judge reward, **same 4B judge as Exp 3** (only the
  policy model changed). Eval base vs checkpoint on same 28 held-out.
- **Train run:** `/Users/adithyagiridharan/Desktop/legal_rl_runs/exp4/`.
  Checkpoint: `tinker://ba82dc9c-dacc-540f-821e-848cb6fdac57:train:0/sampler_weights/final`.

**Observed (held-out 28 Q)**

| 30B | base | after RL | Δ |
|---|---|---|---|
| correctness | 0.643 | 0.500 | −0.143 |
| judge_score | 0.750 | 0.643 | −0.107 |
| turns | 2.64 | 2.39 | −0.25 |

Training reward was **high** (~0.68 mean, batches up to 0.89) — i.e. it fit the
*training* questions well while held-out *dropped*.

**Interpretation**
- **RL regressed the 30B on held-out** (0.64 → 0.50). Not flat — worse. (n=28,
  −0.14 ≈ 1.5 SE; both correctness and judge dropped, same direction.)
- High train reward + lower-than-base held-out = textbook **overfitting**. The
  bigger model had more to lose and fell further. Both RL'd models (4B and 30B)
  converged to exactly 0.50 on held-out → RL collapsing toward the training
  distribution regardless of starting capacity.
- **Two leading, testable causes:**
  1. **Dataset too small (110 Q)** → overfit. Makes dataset expansion empirically
     urgent, not optional.
  2. **LR too high for a 30B** (`4e-5` reused blindly) → can degrade a big model.
     Cheap to test with an LR sweep / lower LR.
- **Key confound (flagged):** the **judge is a 4B model grading a 30B agent** —
  both in training and eval. The 30B may have overfit to the *weak grader's
  quirks*, not true correctness. The base-vs-RL comparison stays internally valid
  (same judge both sides), but a judge weaker than the agent is a real problem.
  Violates the "grader ≥ graded" rule.

**Decision**
- Do not RL the 30B further at this scale/LR/judge. Three concrete next moves,
  roughly in priority:
  1. **Upgrade the judge** to a model ≥ the agent (e.g. 30B+ judge) — we are
     currently violating grader≥graded, which taints both reward and eval.
  2. **Expand the dataset** (more train + a larger frozen eval set for statistical
     power; current n=28 can't resolve the ~0.1 effects we chase).
  3. **LR sweep** on the 30B (try lower LR; current 4e-5 was not tuned).

> **Note added after A5:** the "overfitting regression" interpretation above was
> measured under the 4B judge. A5 (below) re-grades with a strong 235B judge and
> finds the sign **flips** to a small improvement. The Exp 4 observations stand
> *as recorded under the 4B judge*; A5 shows the *interpretation* was judge-
> dependent. Both are kept — the lesson is the trail, not a single verdict.

---

### A5 — Re-grade Exp 4 with a strong judge (judge ≥ agent)
- **Date:** 2026-06-06
- **Motivation:** the Exp 4 reward AND eval used a **4B judge to grade a 30B
  agent** — a "grader < graded" violation. Tested directly whether that
  contaminated the result, before spending on retraining.
- **Method:** re-ran `evaluate.py` for both the 30B base and the 30B+RL
  checkpoint on the **same 28 held-out**, changing only `judge_model` →
  `Qwen/Qwen3-235B-A22B-Instruct-2507` (clearly stronger than the 30B-A3B agent).
  Inference-only; no retraining.

**Observed (30B held-out, 28 Q)**

| correctness | 4B judge | 235B judge |
|---|---|---|
| base | 0.643 | 0.321 |
| +RL | 0.500 | 0.393 |
| **Δ (RL − base)** | **−0.143** | **+0.072** |

(judge_score: base 0.750→0.571, +RL 0.643→0.625 under the stronger judge.)

**Interpretation**
- **The 4B judge was inflating *and* sign-inverting.** It rated the base 0.64
  (vs 0.32 from the strong judge) — lenient, rubber-stamping. And the RL Δ flips
  from −0.143 (4B) to **+0.072 (235B)**: under a trustworthy ruler, RL is a small
  *improvement*, not a regression. A grader weaker than the graded didn't just add
  noise — it flipped the conclusion.
- **Consequence for the whole journal:** every prior absolute number (Exp 2/3/4,
  base evals) was measured under the lenient 4B judge and is therefore inflated.
  The *relative* within-experiment comparisons remain valid (same judge both
  sides), but cross-experiment absolute scores are not trustworthy.
- **Caveat (unchanged rigor):** n=28, SE≈0.09; +0.072 ≈ 0.77 SE — directionally
  positive on both metrics but **not statistically significant**. "RL is not a
  regression and shows a small positive signal," not "RL works."
- **What's preserved (per append-only discipline):** Exp 4's numbers stand as
  recorded under the 4B judge; A5 adds the strong-judge view. The teaching value
  is the *trail* — we watch whether the small RL-helps signal survives a strong
  judge + bigger eval + more data when we scale.

**Decision**
- Judge ≥ agent is now an empirically proven requirement, not a precaution.
- Next big run uses the **strong judge as the reward during training** (not just
  at eval), a **larger frozen eval set** (kill the n=28 noise), scaled rollouts
  (`group_size` 16, more `groups_per_batch`/steps), on the 30B.
- Open follow-up: spot-check a few 235B-judge verdicts against transcripts to
  confirm the strong judge is *accurate*, not merely *stricter*.

---

### Exp 5 — Clean-slate run: all known confounds removed
- **Date:** 2026-06-07
- **Hypothesis:** with every known confound fixed at once, RL will finally show a
  real held-out improvement over base — or, if not, we can trust the null.
- **Design (kitchen-sink, agreed after design review):**
  - **Data:** unified multi-source pool (`use_unified=True`) — isaacus
    legal-rag-qa (US, 138) + legal-rag-bench (AU criminal, 100) +
    open-australian-legal-qa (AU broad, 2,124) = **2,362 QA**; unified ChromaDB
    index of **12,430 chunks** (small 1.5k-char chunks). Split 2,126 train / 236
    eval (deterministic, zero overlap).
  - **Policy:** Qwen3-30B-A3B-Instruct-2507.
  - **Judge (reward AND eval):** Qwen3-235B-A22B-Instruct-2507 — grader ≥ agent,
    fixing the A5 confound. Used as the *training reward*, not just eval.
  - **LR:** 5e-4 (`hyperparam_utils.get_lr` for the 30B) — note this is ~12× the
    4e-5 of Exp 4, so the Exp-4 "LR too high" overfit theory was likely wrong.
  - **KL:** `kl_penalty_coef=0.05`, reference = frozen base (wired
    `KLReferenceConfig`; required, else startup error).
  - **Rollouts:** group_size 8 × groups_per_batch 8 (middle ground — 235B judge
    is slow: 64 judge calls/batch). `max_steps=50`.
- **Pre-registered success bar:** checkpoint beats base on the 236-Q held-out by
  ≥ 0.06 correctness (≈2 SE) under the 235B judge.
- **Run:** `/Users/adithyagiridharan/Desktop/legal_rl_runs/exp5/`. Checkpoint:
  `tinker://4ab56487-c32e-58e0-83d7-ac1e54518d1a:train:0/sampler_weights/final`.
  ~5 min/batch (throttle + slow judge); healthy throughout (turns ~2.3–2.7,
  frac_mixed 0.38–0.88, no hacking collapse).

**Observed (unified 236-Q held-out, 235B judge, base vs checkpoint)**

| | base | +RL (Exp 5) | Δ |
|---|---|---|---|
| correctness | 0.619 | 0.606 | −0.013 |
| judge_score | 0.689 | 0.691 | +0.002 |
| format | 0.983 | 0.992 | +0.009 |
| turns | 2.38 | 2.35 | −0.03 |

**Interpretation**
- **No improvement. Fails the pre-registered ≥0.06 bar** (Δ correctness −0.013 ≈
  0.4 SE at n=236, SE≈0.032 — squarely noise; judge_score flat too).
- **This is the trustworthy null.** Unlike Exp 3/4, every known confound is gone:
  big data (overfit ruled out), strong judge ≥ agent (A5 confound gone), n=236
  eval (power to see 0.06), tuned LR + KL + scaled rollouts. So we can now state
  with confidence: **outcome-judge GRPO does not improve this 30B agent on legal
  RAG QA.**
- **Why (consistent across all 5 experiments):** the instruct base is *already
  competent* (0.619) and *already uses the tool* (A3). RL with an outcome reward
  on near-ceiling behavior has little to teach. The tool helps; the base already
  exploits it; outcome reward can't push past that ceiling.

**Decision / what this rules in**
- Outcome-reward RL on tool-use is **exhausted** for this dataset+model. Stop
  iterating it.
- Genuinely unexplored levers, in priority:
  1. **Process/trajectory reward** — reward *how* it searches (e.g. retrieval-hit
     against ground-truth `relevant_passages`), not just the final answer. The
     one major reward design we never tried.
  2. **A task the base is NOT near ceiling on** — harder/retrieval-necessary
     questions where base starts low (e.g. ~0.3), giving RL real headroom.
- Note the standalone finding: "RL-on-tool-use does not help a strong instruct
  model already competent at the task" is itself a clean, valuable result.

---

### A6 — Failure-mode diagnosis: WHY does the base get held-out questions wrong?
- **Date:** 2026-06-07
- **Motivation:** before choosing the next fork, diagnose the base's errors with
  data instead of assuming. A user observation sharpened the method: "retrieval
  failure" is influenced by the agent's *query* (its action), so a naive
  "needed info not retrieved" bucket conflates two different causes.
- **Method:** `diagnose_failures.py`, 30B base, 40 held-out questions, 235B judge.
  For each WRONG answer the judge does a **retrieval-sufficiency** check on what
  the agent actually retrieved; if insufficient, we **re-retrieve with the literal
  question** (best-case query) and re-check, splitting the cause three ways:
  - reasoning_failure: agent retrieved sufficient info, still wrong.
  - agent_query_failure: agent's query missed it, but the literal question
    retrieves it → the *query* was the problem (RL-fixable).
  - retriever_ceiling: even the literal question can't retrieve it → infra limit.

**Observed (40 held-out, 30B base)**

| | count | share of errors |
|---|---|---|
| correct | 23/40 (57.5%) | — |
| **reasoning_failure** | 8/17 | **47%** |
| retriever_ceiling | 6/17 | 35% |
| **agent_query_failure** | 3/17 | **18%** |

**Interpretation**
- The 57.5% correct matches Exp 5's 0.619 base (within n=40 noise) — consistent.
- **Tool-use RL can address at most the 18% agent-query slice** ≈ a ceiling of
  ~+7.5% correctness even if RL fixed every bad query. This *quantifies why Exp 5
  was flat*: most failures are not about tool use.
- **Reasoning failures dominate (47%)** — the agent had the needed info and still
  answered wrong. That's a model-capability limit; no tool-use reward fixes it.
- **Retriever ceiling (35%)** is an *infra* lever (embeddings/chunking/n_results),
  not RL.
- **Methodological credit:** the query-vs-ceiling split (user's point) flipped the
  read — a naive bucketing would have labeled 9/17 (53%) "retrieval failures" and
  over-sold Fork 1; only 3 of those are actually RL-addressable.
- **Caveat:** n=40 → 17 errors split 8/3/6, small counts, wide bars. Qualitative
  ranking (reasoning ≫ ceiling > query) is clear; exact percentages are rough.

**Decision / refined fork view**
- **Fork 1 (process/query reward):** real but small upside on this dataset
  (~18% of errors). Try it knowing the ceiling is modest.
- **Fork 2 reframed:** the goal isn't merely "harder task" but a task where
  failures are **tool-use-bound, not reasoning-bound** — i.e. good searching is
  THE deciding factor. On legal QA, reasoning decides most errors, so tool-RL has
  little to grab.
- **Cheap non-RL win:** the 35% retriever-ceiling slice is improvable via better
  embeddings / finer chunking / higher n_results — possibly more correctness per
  dollar than any RL here.
- Detail saved: `legal_rl_runs/failure_diagnosis.json`.

---

### Probe — 397B flagship scoping (smoke tests, not a full experiment)
- **Date:** 2026-06-08
- **Goal:** see if a much bigger policy (`Qwen/Qwen3.5-397B-A17B`, 17B active) has
  headroom over the 30B, and stand up a *superior* judge (≥ agent) for it.
- **Smoke (8 held-out Q) — what we learned by NOT running the full job first:**
  - Bug 1: `model_info` has no renderer mapping for
    `nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16` → `KeyError`. Fixed by adding
    an explicit `judge_renderer_name` override (`nemotron3`).
  - Bug 2: with `nemotron3` (thinking on), the 550B judge scored the 397B at
    **0.125** — a judge artifact (thinking tokens pollute the verdict parser).
    Isolated by re-grading with the trusted 235B judge → **0.625**. Fixed with
    `nemotron3_disable_thinking` → 550B judge then also gives **0.625** (the two
    judges now agree — cross-validated).
  - Signal: **397B base ≈ 0.625 ≈ 30B base (0.619)** (n=8). The flagship shows no
    obvious jump — consistent with A6 (task is reasoning/ceiling-bound, not
    capacity-bound at this scale).
- **Status:** 397B + 550B-judge pipeline now works end-to-end. No full 397B run
  yet. The smoke caught a KeyError and a sign-flipping judge bug for ~8 questions
  of cost instead of a multi-hour wasted run.

### A7 — Unified-index retrieval audit (the gap: A1 only covered the OLD index)
- **Date:** 2026-06-09
- **Why:** A1's recall@3=0.775 was on the old single-source index. The unified
  index (12,430 chunks, 3 sources, used by Exp 5+) was never audited. User flagged
  the gap.
- **Method:** `retrieval_audit_unified.py`, 60 questions/source (180 total),
  literal-question query, gold ids mapped into unified space (incl. the
  open-australian dedup logic), recall@k overall + per source.

**Observed (unified index, literal-question query)**

| source | n | r@1 | r@3 | r@5 | r@10 |
|---|---|---|---|---|---|
| ALL | 180 | 0.533 | 0.639 | 0.689 | 0.744 |
| legal-rag-qa | 60 | 0.600 | 0.733 | 0.783 | 0.817 |
| **legal-rag-bench** | 60 | 0.217 | **0.350** | 0.400 | 0.500 |
| open-australian | 60 | 0.783 | 0.833 | 0.883 | 0.917 |

**Interpretation**
- Unified r@3 = 0.639, **down from the old 0.775** — almost entirely because
  **`legal-rag-bench` retrieves terribly (r@3=0.35)**: ~65% of its questions are
  retrieval-unwinnable even with the perfect query. Cause: ultra-granular
  section-level passages among 4,876 similar chunks + hypothetical-scenario
  questions semantically distant from abstract rule text.
- This **explains much of A6's 35% retriever-ceiling** — it's concentrated in
  legal-rag-bench, not a uniform index defect.
- `legal-rag-qa` (0.733) ≈ its standalone 0.775 (minor unified-index distractor
  drop). `open-australian` (0.833) is high but **easy/circular by construction**
  (QA was GPT-4-generated from that exact chunk; answers also model-generated).
- Reconciles with A1: we ruled out "retriever BROKEN," never "retriever perfect."
  The residual miss-rate was always there; A7 localizes it to one source.

**Decision**
- **Drop `legal-rag-bench` from the pool** (100 QA, ~65% retrieval-unwinnable —
  noise in training, drag on eval). Rebuild a cleaner index from legal-rag-qa +
  open-australian (~2,262 QA). Cheaper rebuild (~7,550 chunks vs 12,430).
- Note open-australian's easy/synthetic profile when interpreting its scores.
- NOTE: user chose to KEEP legal-rag-bench in the index for subsequent runs
  (impact modest: 100/2,362 QA). No rebuild done.

---

### Exp 6 (partial) — 397B flagship: base eval + RL killed on cost
- **Date:** 2026-06-09
- **Plan:** RL the flagship `Qwen/Qwen3.5-397B-A17B` (17B active) on the full
  unified index, judge = `Nemotron-3-Ultra-550B-A55B` (`nemotron3_disable_thinking`,
  grader ≥ agent), same recipe as Exp 5. Wired `judge_renderer_name` through the
  training path (legal_env.py / train.py) so the 550B judge resolves.
- **RL run KILLED early (cost decision).** The 397B-policy + 550B-judge config is
  the most expensive by far (~$17 wiped in minutes; full run projected $100+).
  Given (a) Exp 5's clean null on the 30B, (b) A6 (failures are reasoning/
  retriever-ceiling, only 18% RL-addressable), the expected payoff was low — most
  cost on the least-surprising experiment. Killed the RL; kept the bounded base
  eval. *(Cost-vs-expected-information call, recorded on purpose.)*

**397B base, full 236-Q held-out (judge = 550B):**
| | correctness | judge_score | format | turns |
|---|---|---|---|---|
| 397B base | 0.699 | 0.712 | 0.703 | 3.33 |

- Note: the n=8 smoke had said ~0.625 (≈30B) — *misleading small sample*. Full
  n=236 says 0.699. Lesson: don't trust n=8.

### A8 — Resolving the judge confound (does scale actually help?)
- **Date:** 2026-06-09
- **Problem:** 397B@550B (0.699) vs 30B@235B (0.619) = naive +0.080, but different
  judges → confounded (could be real gain or 550B leniency).
- **Method:** the decisive eval — **30B base under the SAME 550B judge**, same
  236-Q. Completes the 2×2.

**2×2 (base correctness, n=236)**

| | 235B judge | 550B judge |
|---|---|---|
| 30B base | 0.619 | 0.653 |
| 397B base | (smoke 0.625) | 0.699 |

**Interpretation — the naive +0.080 decomposes ~half and half:**
- **Judge leniency:** 30B 0.619→0.653 by switching judge = **+0.034** (550B is a
  bit more generous).
- **Real scale gain:** 397B − 30B *both under 550B* = 0.699−0.653 = **+0.046**.
- So ~40% of the apparent "scale win" was the measuring instrument; controlling
  the judge was necessary (third time the judge mattered — cf. A5).
- **Significance:** n=236, SE≈0.031; +0.046 ≈ 1.5 SE → **suggestive, not
  conclusive.** Real-but-modest, not a transformation. Consistent with A6 (a bit
  of the reasoning bucket gets chipped; task stays reasoning/ceiling-bound).

**Project-level model-size finding (base, fixed judge where comparable):**
- 4B ≈ 0.50 → 30B ≈ 0.65 → 397B ≈ 0.70: **scale gives a real but diminishing
  lift on the base**, while **RL on top of any size did not beat its base on
  held-out** (Exp 3 4B null, Exp 5 30B null; 397B RL not run). Net: on this task,
  **a bigger base model is the lever that works; tool-use RL is not.**

---

## 5. Open questions / next steps

**Done:** LLM-judge reward (Exp 2) · held-out protocol + `evaluate.py` (Exp 3) ·
retrieval audit A1 · grounding probe A3 (retrieval IS used — memorization refuted)
· capacity probe A4 (bigger base helps) · RL on 30B (Exp 4 — apparent regression)
· A5 re-grade (weak judge inverted Exp 4's sign) · **Exp 5 — clean-slate run,
trustworthy NULL: outcome-RL does not beat base (0.619→0.606, n=236, strong judge).**

**Confound cleanup: ALL DONE.** judge ≥ agent (235B), big data (2,126 train),
big eval (236, SE≈0.03), tuned LR, KL anchor, scaled rollouts. The measurement
apparatus is now trustworthy. Verdict on outcome-judge GRPO for legal RAG QA:
**no held-out improvement** — the instruct base is already near ceiling and
already uses the tool.

**Next directions (the genuinely unexplored levers):**

1. **Process/trajectory reward (top priority).** Outcome reward is exhausted.
   Reward *how* the agent searches — e.g. retrieval-hit vs ground-truth
   `relevant_passages` (deterministic, group-centered → rewards query quality),
   optionally + grounding ("is the answer supported by retrieved text?"). This is
   the one major reward design never tried. Note: legal-rag-qa & legal-rag-bench
   have gold passage ids; open-australian needs its source chunk treated as gold.
2. **A task the base is NOT near ceiling on.** RL needs headroom. Find/build
   questions where the base scores low (~0.3) — harder multi-hop, or
   retrieval-necessary content the base can't shortcut from pretraining. If base
   starts low, outcome RL may finally have room to work.
3. **Multiple tools** → tool-selection as a learned skill (`build_agent_tool_env`
   already takes a tool list). Richer agentic problem.

**Standing guardrails / smaller items:**
- Keep `turns_per_episode` watched (early reward-hacking signal).
- Spot-check 235B-judge verdicts vs transcripts (accurate, not just stricter?).
- Agent query quality vs literal-question quality (from A1, still untested).

---

## 6. Infrastructure decisions & bugs (chronological)

- **Cohere embed-v4 blocked → switched to Titan.** Cohere on Bedrock requires an
  AWS Marketplace subscription (product id `prod-ft3cj5gst3spo`), which needs a
  credit card; the account's UPI payment instrument was rejected
  (`INVALID_PAYMENT_INSTRUMENT`). Amazon-owned **Titan** embeddings are not
  Marketplace-gated and worked immediately. *(Verified against AWS docs.)*
- **Titan token limit / chunking.** Titan embed-v2 caps at 8,192 tokens **or**
  50,000 chars. `count_tokens` API is **not supported** for embedding models, and
  no public Titan tokenizer exists. Long corpus passages (up to ~261k chars)
  exceeded the limit. Resolved by splitting on paragraph boundaries at a
  conservative 20,000-char cap → 190 passages became 342 chunks, all embedded
  without error. *(Lesson recorded: use a real tokenizer/count API when one
  exists; here neither was available, so a conservative char cap was the
  defensible fallback.)*
- **Dataset has two configs.** `isaacus/legal-rag-qa` exposes `corpus` (190
  passages, for the index) and `qa` (138 QA pairs, for training); only a `test`
  split exists. Initial code assumed a flat `train` split and a
  `relevant_documents` field — both wrong. Fixed to load the right configs.
- **ChromaDB CLI absent → PersistentClient.** The `chroma run` server CLI was not
  available in the installed build; switched to in-process `PersistentClient`
  (no server, no API key), which also removed the 160GB-RAM concern that applies
  only to the full Wikipedia index in the upstream recipe.
- **Wrong model id.** Initial default `Qwen/Qwen3-4B-Instruct` does not exist on
  Tinker; corrected to `Qwen/Qwen3-4B-Instruct-2507` (verified via server
  capabilities).
- **W&B logged nothing despite `wandb_project` set.** `ml_log.setup_logging`
  enables W&B only if the `WANDB_API_KEY` *environment variable* is present; it
  does not read `~/.netrc` credentials from `wandb login`. Fixed by exporting
  `WANDB_API_KEY` in the creds file. Next run will stream live.

---

## 7. Reconciliation vs upstream `search_tool` recipe

`legal_rl` was modeled on `tinker_cookbook/recipes/search_tool`. Verified
equivalent: episode lifecycle, reward formula shape, advantage computation, loss,
pickle `__getstate__`, async/sync boundaries, embedding input/output contract.
Intentional differences: Titan↔Gemini, local ChromaDB↔HTTP ChromaDB, legal
dataset↔SearchR1 dataset, added checkpoint-loading + KL + save_every config.
Not ported: streaming-minibatch support (not needed yet). One fix applied during
reconciliation: added retry/backoff to the ChromaDB query path.
