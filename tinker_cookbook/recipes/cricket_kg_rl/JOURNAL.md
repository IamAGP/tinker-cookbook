# Cricket KG RL — Training Journal

> All runs, bugs, learnings, and decisions recorded in order.
> Goal: Train Qwen3-30B-A3B via RL to answer IPL cricket questions by querying a Neo4j knowledge graph.

---

## Project Overview

**Task:** Multi-turn RL agent that answers natural language cricket questions by writing and executing Cypher queries against a Neo4j graph database containing ball-by-ball IPL T20 data.

**Agent tools:**
- `get_schema()` — fetch graph schema (node labels, relationships, properties, endpoints)
- `run_cypher(query)` — execute a Cypher query, get rows back
- `final_answer(answer)` — submit answer, ends episode, triggers reward

**Model:** `Qwen/Qwen3-30B-A3B` with LoRA rank 16, renderer `qwen3_disable_thinking`

**Stack:** Tinker (Thinking Machines Lab) for GPU training, local CPU for rollouts, Neo4j AuraDB for the KG.

---

## Infrastructure Setup

### Neo4j Schema
The graph has the following structure (discovered by running `CALL db.schema.nodeTypeProperties()` + endpoint queries):

**Node labels:** `Player`, `Team`, `Match`, `Innings`, `Over`, `Delivery`, `BattingPerformance`, `BowlingPerformance`, `Wicket`

**Key relationships:**
- `(Player)-[:BATTING_PERFORMANCE]->(BattingPerformance)-[:PERFORMANCE_IN_INNINGS]->(Innings)`
- `(Player)-[:BOWLING_PERFORMANCE]->(BowlingPerformance)-[:BOWLING_IN_INNINGS]->(Innings)`
- `(Innings)<-[:HAS_INNINGS]-(Match)`
- `(Team)-[:WON_MATCH]->(Match)`
- `(Player)-[:PLAYER_OF_MATCH]->(Match)`
- `(Player)-[:DISMISSED]->(Wicket)`

**Bug found:** `db.schema.nodeTypeProperties()` only returns properties that have constraints or indexes — not all properties. Fixed by sampling actual data nodes instead.

**Bug found:** Rich console was parsing `[propertyName, ...]` as markup tags, eating all property lists silently. Fixed by removing square brackets from schema format string.

**Bug found:** `SHOW INDEXES WHERE ... YIELD` — wrong order. Correct syntax is `SHOW INDEXES YIELD ... WHERE ...`.

### Question Generation (`generate_questions.py`)
Auto-generates (question, answer, Cypher) triples by querying Neo4j directly. Templates cover:
- Top run scorer / wicket taker per season
- Most sixes / fours / dot balls
- Highest individual score
- Best economy rate (min 10 overs)
- Team with most wins
- Player of the Match leader
- Most caught dismissals
- Career batting/bowling stats for top 20 players

**Dataset:** 100 questions generated (`output/questions_20260316_164926.json`).

### Smoke Inference (`smoke_inference.py`)
Used to test the pipeline end-to-end before training:
- Added `_Tee` class to log to file + stdout simultaneously
- Added debug logging for tool call results (decode new `EncodedTextChunk` tokens between turns)
- Suppressed Neo4j notification warnings (`logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)`)

---

## Training Runs

### Run 1 — 2026-03-15-21-45
**Config:** smoke run, 5 steps, 30 questions
**Result:** Superficially promising — reward rose from 0 → 0.32, turns dropped 5.5 → 3.13.
**Mistake:** Gave confidence for full run based on 5 steps without reading logtree files. Too short to expose problems.

---

### Run 2 — 2026-03-16-16-51 / 17-38
Intermediate smoke runs during debugging.

---

### Run 3 — 2026-03-16-18-18 (First "full" attempt, 25 steps)
**Config:** `max_questions=None` (100), `max_steps=50`, `behavior_if_log_dir_exists=delete`
**Stopped at step 24** — dataset was NOT cycling. With 100 questions and `groups_per_batch=4`, there were only 25 unique batches. When exhausted, `done_frac=1.0` and training ended.

**Reward function at this time:**
```python
reward = 0.3 (base, always) + 0.3 (entity match) + 0.4 (number match)
```

**What happened (read from metrics.jsonl + logtree):**

| Steps | turns/ep | reward | frac_all_bad | What |
|-------|----------|--------|--------------|------|
| 0–4   | 5→3      | 0.19–0.39 | 0.75→0.0 | Model querying DB, some entity matches |
| 5–14  | ~3       | 0.06–0.4  | mixed     | Variable, some learning |
| 15–18 | 3→2.5    | 0.3       | 1.0       | Collapse beginning |
| 19–24 | 1.0      | 0.3       | 1.0       | **Full collapse** |

**Root cause — reward hacking:**
The 0.3 base format reward created a guaranteed floor. The model discovered that calling `final_answer()` immediately (without querying the DB) always yields 0.3 — equal to or better than risking DB queries that might still get entity/number wrong. After ~15 gradient updates, 100% of episodes were 1-turn: model receives question → immediately calls `final_answer` → collects 0.3 → episode done.

This is textbook reward hacking. `frac_all_bad=1.0` means zero reward variance across all groups → DAPO skips updates → no learning.

**Best checkpoint from this run:** Step 10 (`tinker://b16c6408.../weights/000010`) — before full collapse.

**Learnings:**
1. Never give a base reward for format/structure that can be gamed by skipping the actual task
2. 5-step smoke runs are too short to reveal reward hacking (it took ~15 steps to manifest)
3. Dataset must cycle — 100 questions / 4 per batch = only 25 steps before exhaustion
4. Always read metrics AND logtree before declaring a run successful

---

### Run 4 — 2026-03-16-18-10
Aborted early (path/directory issue).

---

### Run 5 — 2026-03-16-19-13 (Complete)
**Config:** `max_questions=None` (100), `max_steps=50`

**Fixes applied from Run 3:**
1. **Reward hacking fixed:** Removed 0.3 base reward. New reward = 0 if no `run_cypher` call was made. Otherwise: `0.4 (entity match) + 0.6 (number match)`. Model must query the DB to get any reward.
2. **Dataset cycling fixed:** `CricketKGDataset.__len__` returns 10,000. `get_batch(index)` uses modulo + reshuffle per epoch. Training now runs to `max_steps` without exhausting data.
3. **Conversation logging added:** Every completed episode writes a full record to `{log_path}/conversations.jsonl` including: question, ground_truth, final_answer, used_db, reward, entity_match, number_match, turns, and the complete message history (every tool call, every tool result, every assistant response).
4. **Path fix:** `questions_path` default now uses `__file__`-relative absolute path so it works regardless of which directory the command is run from.

**What happened (read from metrics.jsonl + conversations.jsonl):**

| Steps | turns/ep | reward  | no_db | parse_err | What |
|-------|----------|---------|-------|-----------|------|
| 0–14  | 3–4.3    | +0.19–+0.75 | 0.0 | 0.0 | **Genuine learning** — model queries DB, gets real answers |
| 15+   | 2.3–5.6  | -0.09–+0.19 | 1.0 | 1.0 | **Format collapse** |

Step 9 hit reward=0.75 — a genuinely correct answer with entity + partial number match.
`conversations.jsonl` confirms 125 episodes with positive reward (model queried DB and answered).

**Root cause of collapse at step 15 (diagnosed from conversations.jsonl):**

Two failure modes emerged simultaneously after ~15 gradient updates:

**Mode 1 — Empty response after schema (majority):**
The model calls `get_schema` correctly, receives the schema, then outputs empty text. Episode ends. What happened: after getting the schema, the model generates `<think>...</think>` thinking content (Qwen3 pretraining behavior). The `qwen3_disable_thinking` renderer strips all thinking tokens, leaving an empty assistant message. Framework sees no tool calls → `no_tool_calls=True` → episode over → reward=0.

**Mode 2 — XML tool call format (11 episodes):**
Model writes tool calls as plain text: `<tool_call>{"name": "run_cypher", ...}</tool_call>` instead of structured tool calls. Framework can't parse → `-0.1` parse penalty applied. The Cypher queries inside are also garbled (Korean, Japanese, Chinese characters mixed in — classic hallucination under distribution shift).

**Root cause of both modes:** `kl_penalty_coef = 0.0`. With no KL penalty, the model is free to drift arbitrarily far from its base distribution. After ~15 gradient updates, it reverted to Qwen3's native pretraining format (thinking tags + XML tool calls) which the `qwen3_disable_thinking` renderer cannot handle at training time.

**Best checkpoint from this run:** Step 10 (`tinker://3685091a.../weights/000010`) — before format collapse, captures the best learning from steps 0-9.

---

### Run 6 — 2026-03-17-17-19 (Complete)
**Config:** `max_questions=None` (100), `max_steps=50` (ran as 50, config had 100), `kl_penalty_coef=0.05`, `load_checkpoint_path=tinker://3685091a.../weights/000010`

**Fixes applied from Run 5:**
1. **KL penalty added:** `kl_penalty_coef=0.05` + `kl_reference_config=KLReferenceConfig(base_model="Qwen/Qwen3-30B-A3B")`. Reference is the original base model, keeping the policy's distribution close to Qwen3's natural format.
2. **`kl_reference_config` bug fixed:** Tinker requires this field when `kl_penalty_coef > 0`. It was missing — added `KLReferenceConfig` import and conditional construction in `cli_main`.
3. **Epoch flood logging fixed:** Changed `logger.info` → `logger.debug` for epoch reshuffle messages (training loop pre-scanned large indices before starting, flooding output).
4. **Loaded from Run 5 step 10:** Started from the best pre-collapse checkpoint rather than base model.

**What happened (read from metrics.jsonl + conversations.jsonl):**

| Steps | turns/ep | reward | no_db | parse_err | frac_all_bad | What |
|-------|----------|--------|-------|-----------|--------------|------|
| 0–49  | 3.0–5.1  | 0.0–1.0 | 0.0 | 0.0 | 0.0–1.0 | **No collapse at any step** |

Key numbers from conversations.jsonl (800 total episodes):
- **400 episodes (50.0%)** had reward > 0 — vs 19.7% in Run 5
- **297 episodes (37.1%)** got full credit (reward=1.0, both entity + number matched) — vs 10.4% in Run 5
- **0 episodes (0.0%)** had no DB query — vs 40.2% in Run 5
- **0 parse errors throughout** — format collapse completely prevented

Best steps: step 30 (reward=0.85, entity=1.0), step 44 (reward=1.0, entity=1.0, number=1.0), step 48 (reward=0.75).

**Smoke test on step 30 checkpoint (2026-03-17):**

Question: *"How many total wickets did Rashid Khan take across all IPL seasons in this dataset?"*

Model wrote:
```cypher
MATCH (p:Player {name: 'Rashid Khan'})-[:BOWLING_PERFORMANCE]->(bp:BowlingPerformance)
RETURN SUM(bp.wicketsTaken) AS totalWickets
```
Got back `107`. Final answer: "Rashid Khan took a total of 107 wickets across all IPL seasons." ✓ (verified against Neo4j directly)

**Remaining gap:** Season-specific questions (e.g. "most runs in IPL 2018") still fail — the model aggregates career totals instead of filtering through `BattingPerformance → Innings → Match` by `Match.season`. It knows the schema but hasn't yet learned the season-filter join pattern reliably.

**Best checkpoint from this run:** Step 30 (`tinker://e6c3eb80-28f6-56d5-88dd-3f35f6dea45a:train:0/weights/000030`)

---

### Run 7 — 2026-03-18-16-26 (Stopped early at step 54)
**Config:** `max_questions=None` (100), `max_steps=100`, `kl_penalty_coef=0.05`, `load_checkpoint_path=tinker://e6c3eb80.../weights/000030` (Run 6 step 30)

**What happened (read from metrics.jsonl + conversations.jsonl):**

| Steps | turns/ep | reward | no_db | frac_all_bad | kl | What |
|-------|----------|--------|-------|--------------|----|------|
| 0–12  | 3.0–6.3  | 0.0–0.75 | 0.0 | 0.25–1.0 | 0.08–0.28 | Some learning, model querying DB |
| 13+   | 2.0      | 0.0    | 1.0   | 1.0          | 0.31–1.30 | **Full collapse** — no DB queries |

717 total episodes logged before stopping:
- **29 episodes (4.0%)** had reward > 0 — vs 50% in Run 6
- **20 episodes (2.8%)** got full credit
- **504 episodes (70.3%)** had no DB query — collapse dominated

**Root cause (diagnosed from conversations.jsonl + codebase + web research):**

The collapse is a **thinking token collapse**, distinct from the format collapse in Run 5. The `qwen3_disable_thinking` renderer works by injecting an empty `<think>\n\n</think>\n\n` block into the observation header — it's a **signal**, not a hard constraint. During RL training, as the model drifts from base weights, it starts generating actual thinking tokens (`<think>...</think>`) despite the signal. The renderer strips them from the visible output, leaving an **empty assistant message**. Framework sees no tool call → episode ends → reward=0.

This is a documented phenomenon in the research literature — ICCV 2025 (GTR paper) calls it "thought collapse": thinking tokens are unsupervised during RL (only `final_answer` gets reward signal), so they can drift unpredictably.

**Why KL=0.05 didn't prevent it:**
- Run 6 started from Run 5 step 10 (10 gradient updates from base). KL stayed 0.04–0.38.
- Run 7 started from Run 6 step 30 (40 total gradient updates from base). KL rose to 0.75–1.30 by step 18.
- The further from base, the weaker KL=0.05 is as a regularizer. The model was already in a regime where thinking tokens emerged under RL pressure.

**Key technical finding (from codebase):** `qwen3_disable_thinking` injects the empty think block only into the **header** (weight=0, no loss). During RL, thinking tokens in the model's output receive gradients from the full trajectory loss — they're not masked. So the model can learn to generate thinking despite the header signal.

**Best checkpoint from this run:** Step 3 (`reward=0.75`) — only 3 steps of useful learning before KL started rising.

---

## Key Learnings (Cumulative)

### Reward Design
- **Never give base/format rewards** for actions the model can do trivially (calling any tool). This creates a floor the model will exploit.
- **Gate rewards on task-relevant behavior.** If the task requires DB queries, reward=0 unless the DB was queried.
- **Fine-grained decomposition** (entity + number) gives denser gradient signal than binary 0/1.
- **Reward hacking manifests as**: `frac_all_bad → 1.0`, `turns_per_episode → 1.0`, `reward/total → constant`.

### Dataset / Training Loop
- **Dataset must cycle.** A finite dataset without cycling silently limits training to `len(dataset)/batch_size` steps even if `max_steps` is higher.
- **Use `max_steps` to control training length**, not dataset size.
- **Shuffle on each epoch** to prevent the model memorizing question order.

### Model Stability (Qwen3 specific)
- **`kl_penalty_coef = 0.0` is dangerous** for multi-step RL. The model can drift far enough to lose tool call formatting.
- **`qwen3_disable_thinking` is a signal, not a hard constraint.** It injects an empty `<think>\n\n</think>\n\n` into the observation header (weight=0). During RL, as weights drift from base, the model can start generating actual thinking tokens regardless of this signal.
- **Two distinct collapse modes for Qwen3:**
  - *Format collapse* (Run 5): `kl=0.0`, model reverts to XML tool calls + garbled Cypher. Signature: `parse_error→1.0`.
  - *Thinking token collapse* (Run 7): KL insufficient for drift distance, model generates `<think>` tokens, renderer strips them → empty assistant message → episode ends. Signature: `no_db_query→1.0`, `turns→2`, empty `final_answer` in conversations.jsonl.
- **KL penalty effectiveness depends on starting distance from base.** `kl=0.05` held Run 6 (started 10 steps from base). Failed Run 7 (started 40 steps from base, KL rose to 1.3).
- **KL penalty (0.01–0.1)** is the standard fix. Start at 0.05, but increase if starting from a far checkpoint.
- **Thinking token collapse is documented in literature** — GTR (ICCV 2025), NAACL 2025. Thinking tokens receive no reward signal during RL and are unsupervised, making them prone to drift.

### Debugging / Observability
- **Read `metrics.jsonl` after every run** before drawing conclusions. Scalar trends reveal collapse patterns immediately.
- **Read `conversations.jsonl`** to diagnose WHY. Shows exact tool calls, Cypher queries, tool results, and model answers per episode.
- **`logtree.json` / rollout_summaries.jsonl** from Tinker framework only contain token counts and metrics — NOT the actual model text. Conversation content must be logged separately (via reward_fn).
- **5-step smoke runs are insufficient** for detecting reward hacking or format collapse. Both manifested at step 15+.
- **Best checkpoint ≠ final checkpoint.** Always check metrics to identify which step had best reward before any collapse.

### Tinker-specific
- **Checkpoint deletion:** `uv run tinker checkpoint delete <tinker_path> [--yes]` — checkpoints contribute to billing.
- **`save_weights_for_sampler` vs `save_state`:** sampler_weights is what you load into a new sampler client.
- **`behavior_if_log_dir_exists`:** valid values are `delete`, `resume`, `ask`, `raise` (not `overwrite`).
- **`done_frac`:** fraction of `max_steps` completed, not fraction of dataset.

---

## Tinker Checkpoint Registry

| Run | Date | Steps | State path | Sampler path | Notes |
|-----|------|-------|------------|--------------|-------|
| Run 3 | 2026-03-16-18-18 | 10 | `tinker://b16c6408-952e-56cf-b410-35624c49a168:train:0/weights/000010` | `...sampler_weights/000010` | Best from Run 3, pre-collapse |
| Run 3 | 2026-03-16-18-18 | 20 | `tinker://b16c6408-952e-56cf-b410-35624c49a168:train:0/weights/000020` | `...sampler_weights/000020` | Post-collapse, do not use |
| Run 3 | 2026-03-16-18-18 | final (25) | `tinker://b16c6408-952e-56cf-b410-35624c49a168:train:0/weights/final` | `...sampler_weights/final` | Post-collapse, do not use |
| Run 5 | 2026-03-16-19-13 | 10 | `tinker://3685091a-8e6d-5820-939d-12f550336650:train:0/weights/000010` | `...sampler_weights/000010` | Used as starting point for Run 6 |
| Run 5 | 2026-03-16-19-13 | 20 | `tinker://3685091a-8e6d-5820-939d-12f550336650:train:0/weights/000020` | `...sampler_weights/000020` | Post-collapse, do not use |
| Run 5 | 2026-03-16-19-13 | 30 | `tinker://3685091a-8e6d-5820-939d-12f550336650:train:0/weights/000030` | `...sampler_weights/000030` | Post-collapse, do not use |
| Run 6 | 2026-03-17-17-19 | 30 | `tinker://e6c3eb80-28f6-56d5-88dd-3f35f6dea45a:train:0/weights/000030` | `...sampler_weights/000030` | **Best overall** — reward=0.85, entity=1.0, no collapse |
| Run 6 | 2026-03-17-17-19 | 44 | `tinker://e6c3eb80-28f6-56d5-88dd-3f35f6dea45a:train:0/weights/000044` | `...sampler_weights/000044` | Perfect step (reward=1.0) but may be lucky batch |
| Run 6 | 2026-03-17-17-19 | final (50) | `tinker://e6c3eb80-28f6-56d5-88dd-3f35f6dea45a:train:0/weights/final` | `...sampler_weights/final` | No collapse, safe to use |
| Run 7 | 2026-03-18-16-26 | 3 | `tinker://` (check checkpoints.jsonl) | — | Only useful steps before KL drift |
| Run 7 | 2026-03-18-16-26 | stopped at 54 | — | — | Thinking token collapse from step 13, do not use |

---

## Open Questions

1. ~~Does loading from step 10 + KL=0.05 prevent the format collapse at step 15?~~ **Yes — confirmed by Run 6. Zero format collapse across all 50 steps.**
2. Is the format collapse specific to `qwen3_disable_thinking`? Would a different renderer be more stable?
3. Can we improve the reward function further — e.g., partial credit for a valid Cypher that returns results even if the final answer is wrong?
4. Should we add more question templates to increase dataset diversity?
5. Can the model learn the season-filter join pattern with more steps? Run 7 collapsed before we could find out.
6. ~~Is 50 steps enough?~~ **More steps alone aren't sufficient — stability must be solved first.**
7. **NEW:** How to prevent thinking token collapse when starting from a checkpoint far from base? Options: stronger KL (0.1–0.2), earlier starting checkpoint, `/no_think` in system prompt, or switching to `Qwen3-30B-A3B-Instruct-2507` which has thinking more firmly suppressed.
8. **NEW:** Is SFT warmup on correct season-filter trajectories the right path to seed the multi-hop join pattern before RL?

---
---

# ═══ PROJECT REVIVAL — 2026-06-25 ═══

> Everything above is the **March 2026 attempt** (Runs 1–7, on the old/smaller
> graph with `Qwen3-30B-A3B-Instruct-2507` + `qwen3_disable_thinking`, which hit
> format/thinking-collapse instability). Preserved append-only. This section is a
> fresh start on a new full dataset + a new small model, carrying the relevant
> March learnings forward. Same rigor conventions as the legal_rl journal
> (Observed / Interpretation / Decision; held-out gating; verify-don't-trust).

## What changed since March
- **New full dataset** on AuraDB Professional: ~373,134 nodes, 1,169 IPL matches,
  771 players (March was a smaller graph).
- **Model lineup changed (post 2026-06-12):** the March base
  `Qwen3-4B-Instruct-2507` is **deprecated**. Now targeting a **small** model,
  `Qwen/Qwen3.5-9B`, for the headroom story ("can RL lift a small model on hard
  Cypher").
- **Division of labor:** data-gen by a separate Claude Opus 4.8 (cricket-analytics
  repo, Neo4j MCP); env/eval/SFT/RL/Tinker by this Claude.
- **Lessons carried from the legal-RL project** (see project_legal_rl_blog memory):
  baseline-first, held-out gating, smoke-test-first, diagnose-before-iterating.
  Crucial difference: legal-RL needed an LLM judge (confound hell); **here the
  reward is deterministic (Neo4j ground truth) — NO judge.**

## Fixed setup (revival)
- **Reward:** deterministic — entity-match + number-match vs *execution-verified*
  gold; **0 if no DB query** (anti-hack, carried from March). No judge.
- **Gold (from data-gen Claude):** 1,141 execution-verified pairs →
  train 913 / **eval 228 frozen (content-hashed)**. Ladder: easy 348 / medium 400
  / hard 393; 16 question types. Schema:
  `{id,question,difficulty,type,gold_cypher,gold_answer,entities,numbers,split}`.
- **Harness:** `baseline_eval.py` (CypherTool→Aura, by-difficulty headroom map,
  live progress logging). Creds read from the cricket-analytics AuraDB file, never
  copied into the repo.

## V — Verification before trusting (verify-don't-assume)
- **Live schema** pulled (`get_neo4j_schema`): dual granularity — ball-by-ball
  `Delivery` (`(Player)-[:FACED]->(Delivery)<-[:BOWLED]-(Player)`) + pre-aggregated
  `*Performance`. Old March schema assumptions hold, but re-confirmed not trusted.
- **Gold robustness:** pre-aggregated == ball-by-ball sum (8/8 sample) → gold safe
  either query path.
- **Independent gold audit:** re-executed 30 of her cyphers via my own driver →
  **30/30 match** her stored numbers.
- **Connection:** driver→Aura from tinker venv OK (373,134 nodes).
- **Model lineup** re-queried live (26 models; small candidates Qwen3.5-4B/9B,
  Qwen3-8B, gpt-oss-20b).

## Baseline B1 — Qwen3.5-9B zero-shot, 228 frozen eval (2026-06-25)
**Observed** (run 1):

| tier | n | correct | entity | number | no_query | turns |
|---|---|---|---|---|---|---|
| easy | 69 | 0.913 | 1.000 | 0.913 | 0.000 | 2.23 |
| medium | 91 | 0.571 | 0.593 | 0.571 | 0.000 | 3.91 |
| hard | 68 | 0.147 | 0.426 | 0.162 | 0.000 | 4.79 |
| ALL | 228 | 0.548 | 0.667 | 0.553 | 0.000 | 3.67 |

**Reproducibility re-run** (same 228, confirming run 1 wasn't a fluke — run 1 took
8.5 min, repro ~45 min purely from Tinker sampling-throughput variance, *same
answer*): easy 0.942 / medium 0.527 / hard 0.118 / ALL 0.531. All tiers within
±0.04 → **legit & stable.**

**Interpretation**
- **`no_query = 0` at scale → SFT is NOT needed** (answers March Open Q #8). The
  9B tool-calls Cypher on every question; go straight to RL.
- **Real headroom, the opposite of legal-RL's no-headroom null:** easy ~0.93
  (ceiling), medium ~0.55, **hard ~0.13** (huge room).
- **Hard failure mode is RL-addressable:** entity ~0.45 but number ~0.13 → the
  model names the right players but **computes the wrong stat** (wrong ball-by-ball
  aggregation Cypher) — query-logic error, not a reasoning ceiling.
- Favorable regime: deterministic reward + tool-bottlenecked + genuine headroom.

**Decision / next**
- **Skip SFT. Go straight to RL (GRPO)** on the 913 train split, deterministic
  reward, **gate on the frozen 228 eval**, target the hard tier (0.13 → ?).
- Carry March scars: watch for format/thinking collapse (March Runs 5–7); 9B +
  Qwen3.5 family may behave differently; a small KL anchor (~0.05) helped in March.
- **Pre-register a success bar before launching RL** (e.g. hard-tier correct beats
  base 0.13 by ≥ X on the 228 eval). To be set with the user.

## Open questions (revival)
1. Does straight RL (no SFT) lift the hard tier on held-out, or plateau like
   legal-RL? (The headroom + verifiable reward say it *should* — first real test.)
2. Best small base: 9B (current) vs 4B (smaller, more headroom, cheaper)? Baseline
   4B too?
3. Reward shaping: pure outcome (entity+number) vs partial credit for a valid
   query that returns rows (March Open Q #3)?
4. Does the Qwen3.5-9B avoid the March thinking-collapse instability?

## Exp R1 — pure RL (GRPO), Qwen3.5-9B, no SFT (2026-06-25)

**Setup** (`cricket_rl.py`, log_path `~/Desktop/cricket_rl_runs/r1`, W&B run
`cm15m12z`):
- Policy Qwen3.5-9B, LoRA rank 32. Train on the 913 train split.
- Reward: graded deterministic = 0 if no query, else `0.4*entity + 0.6*number`
  (denser than binary; strict `correct` logged as metric). No judge.
- **LR 1e-5** (multi-turn RL guidance — the 50× correction from get_lr's 5e-4 SFT
  value; see lesson below), **KL 0.05** anchor, on-policy `importance_sampling`,
  group_size 8 × groups_per_batch 8, `remove_constant_reward_groups=True`,
  max_steps 60, save_every 10. GRPO grouping correct: one question → 8 rollouts.

**Run notes:** smoke (2 steps) passed — agentic error-recovery confirmed live
(model wrote bad Cypher → got Neo4j error → self-corrected). Full run was
**painfully slow** (Tinker sampling-throughput variance: batches ~1 min to ~30+
min; ~6 h for 51/60). Killed at batch 51; **gated the step-50 checkpoint** (resume
50→60 verified possible via same log_path — `get_last_checkpoint` finds the
step-50 `state_path`).

**Training signal:** graded reward/total trended UP first-5 0.270 → last-5 0.365
(peaked ~0.47 mid-run; noisy per-batch). KL 0.0003–0.0006 (rock stable, ≪0.01),
turns ~3.8 (healthy multi-turn). **No thinking/format collapse** — answers March
Open Q #4: yes, 9B+Qwen3.5+KL-anchor avoids the March instability.

**Gate — step-50 vs base on the frozen 228 eval** (base = avg of the two baseline
runs). First HELD-OUT improvement in the project:

| tier | base | RL step-50 | Δ | rel |
|---|---|---|---|---|
| easy | 0.928 | 0.928 | +0.00 | (at ceiling) |
| medium | 0.549 | 0.637 | +0.088 | +16% |
| hard | 0.133 | 0.206 | +0.073 | **+55%** |
| ALL | 0.540 | 0.596 | +0.056 | +10% |

`no_query=0` (tool-use preserved). Every non-ceiling tier moved up.

**Vs pre-registered bar:** hard ≥0.25 → 0.206 (just short); ALL ≥0.60 → 0.596
(≈met). Narrowly missed the bars, but the direction is unambiguous.

**Interpretation**
- **RL works in this regime** — thesis holds: tool-bottlenecked + verifiable reward
  + real headroom → RL lifts held-out (opposite of legal-RL's null,
  [[project_legal_rl_blog]]). hard 0.13→0.21 is the money result.
- **Statistical honesty:** hard n=68, +0.073 ≈ 1.5 SE — suggestive, not bulletproof
  on that tier alone. Shored up by (a) ALL=0.596 exceeding base run-to-run noise
  (0.531–0.548), (b) consistency (medium AND hard AND overall all up).
- Only step-50 (killed at 51); full 60 likely crosses the bar.

**LESSON (carry everywhere): RL LR ≠ SFT LR.** `get_lr()` returns the SFT LR
(~5e-4 for Qwen LoRA); multi-turn RL wants ~1e-5 (skills/research/references/
hyperparams.md:86). **Legal-RL Exp 5 used get_lr's ~5e-4 for 30B RL — ~50× too
high — a plausible contributor to that null.** Verified vs the post-merge skills
(latest, dated 2026-05-21).

**Decision / next (pending user):** (1) resume 50→60 to complete the pre-registered
run and see if it crosses the bar; (2) bank R1 as a real positive; (3) R2 variants
(4B base for more headroom/cheaper; async+CISPO for speed; harder hard-tier focus).

### R1 completion — resumed 50→60 + step-60 gate (2026-06-25)

Resume worked cleanly (`behavior_if_log_dir_exists=resume` → `get_last_checkpoint`
loaded step-50 state, "Resumed training from ...weights/000050", trained 50→60).

**Step-60 gate vs base vs step-50 (frozen 228 eval):**

| tier | base | step-50 | step-60 (final) |
|---|---|---|---|
| easy | 0.928 | 0.928 | 0.957 |
| medium | 0.549 | 0.637 | **0.670** |
| hard | 0.133 | 0.206 | **0.118** |
| ALL | 0.540 | 0.596 | 0.592 |

**REVISED VERDICT (supersedes the optimistic step-50 read above — earlier entry
kept append-only for the record):**
- **Did NOT cross the pre-registered bar.** hard ≥0.25 → no (peak 0.206, final
  0.118); ALL ≥0.60 → just under (0.592).
- **Medium is the robust, real win:** 0.549 → 0.637 → 0.670, monotonic, n=91.
- **Hard did NOT reliably improve:** 0.133 → 0.206 → 0.118, non-monotonic, n=68 —
  the step-50 lift did NOT replicate; consistent with NOISE, not durable learning.
  **Lesson: don't trust a single intermediate checkpoint's gain — step-50 alone
  would have over-claimed.** The bounce is why we gate multiple checkpoints.
- **Possible reward-gaming on hard:** at step-60, hard entity=0.500 (↑) but
  number=0.118 (↓) — model got better at *naming* players, worse at *computing* the
  stat. The dense `0.4*entity` term likely incentivizes confident naming without
  solving the query. **R2 reward fix candidate:** drop/shrink the entity term, or
  gate entity credit on a correct number (require the hard query to actually run
  and return the right value).

**Honest bottom line:** pure RL gave a **modest, stable overall lift (0.54→0.59)
driven by the medium tier**; the hardest ball-by-ball queries — the real headroom —
were NOT durably improved by this reward shape. A genuine (if partial) positive vs
legal-RL's flat null, but not the clean hard-tier win step-50 teased.

### Open questions (post-R1)
1. Is the hard tier a reward-shape problem (entity-gaming) or a capability ceiling
   (9B can't compose the ball-by-ball Cypher)? → R2 with number-gated reward
   isolates this.
2. Would SFT warmup on a few correct hard trajectories seed the patterns RL can't
   discover on its own (the 0%-success subtypes RL is blind to)?
3. 4B base: more headroom (lower start) → bigger visible RL delta, cheaper?
4. async+CISPO to escape the brutal sampling-speed tax (R1 took ~6h+ for 60 steps).

## Exp S1 — SFT warmup on HARD-ONLY trajectories (2026-06-26)

**Setup** (`cricket_sft.py`, log_path `~/Desktop/cricket_rl_runs/sft1`, W&B
`tfm9xwjj`): Qwen3.5-9B, LoRA 32, SFT LR `get_lr`≈4.7e-4, 3 epochs.
- Data: her 325 hard-train demonstration trajectories
  (`cricket-analytics/data/sft/hard_trajectories.jsonl`), execution-verified,
  tool_call query = exact gold_cypher, 3 reasoning variants/type. Independently
  re-validated: 0 eval contamination, 0 query mismatches, structure clean.
- Loader: per-assistant-message split (650 examples) + tool_call coercion +
  loss-mask on assistant tokens only (tool results MASKED — model never trained to
  produce DB output). Verified offline.
- **Train loss 0.845 → ~0.01** (near-perfect fit = over-memorized; flag).

**Gate — SFT-only vs base on frozen 228:**

| tier | base | SFT-only (hard) |
|---|---|---|
| easy | 0.928 | 0.739 ↓ |
| medium | 0.549 | **0.000** ↓↓ |
| hard | 0.133 | **0.956** ↑↑ |
| ALL | 0.540 | 0.509 (net worse) |

**CATASTROPHIC FORGETTING — confirmed mechanistically.** Inspected a medium
question ("runs SV Samson scored in IPL 2020/21", gold 375): the SFT model ran a
**hard-style ball-by-ball query** (`...->(:Delivery)<-[:FACED]-(Samson)`), **ignored
the season filter**, and returned his **career** total (4704) instead of the season
(375). entity=0.99 everywhere but number cratered on medium; turns collapsed to
~2.0 across all tiers. The hard-only diet made the model apply ball-by-ball queries
to EVERYTHING, overwriting season-filter / `BattingPerformance` knowledge.

**Two findings (this failure is highly informative):**
1. **Hard patterns ARE learnable: 0.13 → 0.96.** The 9B can do hard ball-by-ball
   Cypher when shown how → **hard was never a capability ceiling.** Pure-RL (R1)
   failed on hard because RL never *discovered* those patterns (0% exploration),
   not because the model couldn't. SFT is the right tool to inject them. (Answers
   post-R1 OQ #1: discovery problem, not ceiling.)
2. **Hard-ONLY SFT catastrophically narrows the model** → forgets medium/easy.
   Textbook OOD forgetting ([2509.12235]). Net ALL slightly worse → unusable as-is.

**Validated the gating discipline:** gating SFT-only *before* RL caught the
catastrophe for the price of one cheap SFT, not a wasted RL run on a broken ckpt.

**Decision / next:** fix = **balanced-mix SFT (hard + medium + easy) + milder
training** (1 epoch / lower LR — 0.01 loss = overfit). Her medium+easy trajectories
now NEEDED — to *preserve* those tiers during SFT, not improve them. Then gate
mixed-SFT → RL from it. Optional side-test: RL from the S1 hard-only ckpt to see if
RL *heals* the medium forgetting ([2509.12235] hypothesis); lower priority than the
mixed fix. SFT-only-hard ckpt: `tinker://cb43cdd9-...:train:0/sampler_weights/final`.

## Exp S2 — mixed-tier SFT (hard+medium+easy) (2026-06-27)

**Setup** (`cricket_sft.py`, log_path `~/Desktop/cricket_rl_runs/sft2`, W&B
`h98v92iq`): Qwen3.5-9B LoRA 32, balanced mix **913 trajectories
(hard 325 / medium 309 / easy 279)** → 1826 examples, 2 epochs (milder than S1's 3),
LR get_lr. Her medium/easy trajectories teach the *boundary* ("season total → use
pre-aggregated BattingPerformance + season filter, NOT ball-by-ball"). Loss
1.00→0.023. All three tier files independently re-validated (0 eval contamination,
0 query≠gold).

**Gate — base vs S1(hard-only) vs S2(mixed) on frozen 228:**

| tier | base | S1 hard-only | S2 mixed |
|---|---|---|---|
| easy | 0.928 | 0.739 | 0.942 |
| medium | 0.549 | 0.000 | **0.967** |
| hard | 0.133 | 0.956 | **0.941** |
| ALL | 0.540 | 0.509 | **0.952** |

**Forgetting fixed** (medium 0.00→0.97) and every tier ~0.94–0.97. Crushes the
pre-registered bar (hard≥0.25→0.94; ALL≥0.60→0.95). `no_query` 0.018 (tiny; a few
easy answered from memory), turns ~2.0 (single clean query/type learned).

**CRITICAL CAVEAT — what 0.95 actually means (don't overclaim).** The eval is
**IN-DISTRIBUTION w.r.t. question FORM**: train and eval share the SAME ~16
templates, only entities (player/season) differ. Verified directly, e.g.
head_to_head TRAIN "how does MS Dhoni fare against SP Narine (...)" vs EVAL "how
does SR Watson fare against Sandeep Sharma (...)" — identical template, swapped
names. So S2's 0.95 measures **entity generalization within learned templates +
correct entity extraction + valid query construction** — a real, useful skill (great
for a *product* serving these 16 question types) — but **NOT** out-of-distribution
generalization to novel question forms/types. This is textbook **"SFT memorizes"**
([2501.17161]): the eval rewards reproducing the right template, which SFT does
near-perfectly.

**Project arc so far (the real story):**
- base: fails hard (0.13), ALL 0.54.
- pure RL (R1): modest+fragile (hard 0.21, ALL 0.59) — RL couldn't *discover* the
  hard query templates.
- SFT hard-only (S1): catastrophic forgetting (medium→0).
- SFT mixed (S2): **ALL 0.54→0.95 in-distribution** — SFT *shows* the templates RL
  couldn't discover. For a templated verifiable task, **SFT ≫ pure RL.**

**Decision / next:** the meaningful open question is now **generalization**, not more
in-distribution lift. Build an **OOD eval** (paraphrased questions = same answers
new wording; and/or HELD-OUT question TYPES never in train) and re-gate base / RL /
S2-SFT / SFT+RL on it. Hypothesis (per [2501.17161]): SFT's edge shrinks OOD and
RL's generalization may matter there — the "SFT memorizes, RL generalizes" test on a
real task. Mixed-SFT ckpt: sampler `tinker://a061bcc4-...:sampler_weights/final`,
state `.../weights/final`. RL-from-SFT has tiny in-distribution headroom now (0.95);
only worth running against the OOD eval.

## Exp G1 — Generalization gate: base / pure-RL / mixed-SFT × 3 eval distributions (2026-06-27)

OOD eval sets (her gen, independently validated: 0 train/eval overlap):
`ood_paraphrase` (89, same 16 patterns reworded, gold unchanged) and
`ood_heldout_type` (96, SIX genuinely new query patterns ∉ trained 16). All run as
INFERENCE on the existing checkpoints (no training). Added per-type reporting to
baseline_eval (`by_type=True`).

**Money table — ALL correct:**

| checkpoint | in-dist (228) | paraphrase (89) | held-out-type (96) |
|---|---|---|---|
| base | 0.540 | 0.461 | 0.167 |
| pure-RL (R1) | 0.592 | 0.562 | 0.188 |
| mixed-SFT (S2) | **0.952** | **0.843** | **0.229** |

**The generalization gradient (SFT): 0.95 (new entities) → 0.84 (new wording) →
0.23 (new query structure).** Reads precisely:
- **Generalizes across ENTITIES** (in-dist 0.95) and **across WORDING** (paraphrase
  0.84, vs base 0.46 / RL 0.56 — incl. hard paraphrase SFT 0.70 while base & RL =
  0.067). So it learned the *semantic* question→query mapping for the 16 patterns,
  not brittle surface strings.
- **Does NOT generalize across STRUCTURE:** on genuinely new patterns SFT 0.23 ≈
  base 0.17 ≈ RL 0.19. **The in-dist 0.95 was largely template memorization** —
  confirmed. ("SFT memorizes", [2501.17161].)

**Per-type on held-out (SFT correct / entity):**
- fielder_dismissals 0.93/1.00 — but base ALSO 0.87 → schema-obvious, not SFT
  generalization.
- most_sixes_in_season 0.44/0.44 — modest real transfer (base 0.17).
- partnership_runs 0.00/1.00 · bowling_in_phase 0.00/0.94 · boundary_pct_powerplay
  0.00/0.87 · win_pct_batting_first 0.00/0.71 — **confidently WRONG**: SFT names the
  right entities but computes a wrong number in ~2.5 turns (pattern-matches the novel
  question to a memorized template, fires the wrong query). Base instead FLAILS (low
  entity, 5+ turns) — equally ~0 correct.

**Verdict:** neither SFT nor (our weak) pure-RL **compositionally generalizes** to
unseen query structures. SFT's huge win is real but **bounded to the 16 trained
patterns** (robust to entity + wording). The "RL generalizes" half did NOT appear —
because R1 was modest/fragile.

**Open question (for next session, NO training launched per user):** can a STRONGER
RL, or **SFT+RL** (RL from the S2 ckpt), teach compositional generalization that SFT
alone can't — i.e., move held-out-type above 0.23? That is now THE experiment. The 4
zero-types (partnership/bowling-phase/boundary%/win%-first) are the target. Reward
redesign (entity-gaming: high-entity/0-number on novel types) also relevant.

## Exp G2 — SFT+RL (RL from S2 ckpt) + number-gated reward (2026-06-27)

**Reward redesign first:** replaced the gamed `0.4*entity + 0.6*number` with
**number-gated** reward = 0 if no query else `number_frac` (fraction of gold numbers
correct; entity earns NOTHING). Verified: name-only/bogus-number 0.4→0.0, all-correct
→1.0. (Closes the Exp G1 "confidently wrong" loophole.) `score()` now also returns
`number_frac`; eval metric still strict `correct` (entity AND number).

**Run** (`cricket_rl.py load_checkpoint_path=<S2 weights/final>`, log `sftrl1`, W&B
`hgswy7po`): Qwen3.5-9B, LR 1e-5, KL 0.05, 8×8, 50 steps. Train reward flat
0.844→0.833 (in-dist already near-ceiling from SFT). Ckpt sampler
`tinker://b6c2b8f6-...:sampler_weights/final`.

**FINAL MATRIX (ALL correct):**

| checkpoint | in-dist | paraphrase | held-out-type |
|---|---|---|---|
| base | 0.54 | 0.46 | 0.17 |
| pure-RL (R1) | 0.59 | 0.56 | 0.19 |
| mixed-SFT (S2) | 0.95 | 0.84 | 0.23 |
| **SFT+RL** | **0.97** | **0.85** | **0.33** |

**PREDICTION WAS WRONG (logged honestly):** I predicted held-out stays ~0.23; it
moved to **0.33** (+0.10). RL-on-top helped more than expected.

**Where the held-out gain came from (per-type, SFT+RL):**
- **most_sixes_in_season 0.44→0.94** — basically the entire gain.
- fielder_dismissals 1.00 (already easy).
- partnership_runs / bowling_in_phase / boundary_pct_powerplay / win_pct_batting_first
  = **0.00** still — the 4 genuinely-novel STRUCTURES unchanged.

**Refined finding:** RL adds compositional generalization **only for novel types that
recombine TRAINED elements** (most_sixes = sixes + season-filter + ranking, all seen
separately) — NOT for types needing genuinely new query structures (pair-at-crease
partnership, phase-filtered BOWLED, innings-order win%). So "RL generalizes" is real
but **bounded to near-compositions**; far-novel structures need broader training
diversity or demonstrations of those patterns.

**Project arc complete (clean publishable story):** base → pure-RL (fragile) →
SFT-hard (catastrophic forgetting) → SFT-mixed (memorizes 16 templates; robust to
entity+wording, not structure) → SFT+RL (best everywhere; extends to near-compositions
but not far-novel structures). The 4 zero-types are the precise frontier.

**Next (user takes over tomorrow):** (a) chase the 4 zero-types via broader training
diversity (more query patterns) or targeted demonstrations; or (b) write up — the
matrix + per-type frontier is figure-ready (claim→evidence→figure, like
[[project_legal_rl_blog]]). Nothing running.

## Data & Methodology — the diverse-trajectory corpus (2026-06-27→28)

Records HOW the training data was built (the "Methods" for the writeup) + the
findings that came out of building it. Two generations of SFT data:

**Gen 1 — deterministic template scripts (913 trajectories).** Python slot-fill:
16 fixed question forms × entities, 3 reasoning variants/type, single-query
(4-message) trajectories, tool_call = exact gold_cypher. Fast, clean — but
*templated*, which is exactly what produced the memorization ceiling (Exp S2/G1:
robust to entity+wording, not structure).

**Gen 2 — genuine agentic authoring (130 trajectories, 124 distinct structures).**
The data-gen Claude (Opus 4.8) *authored each trajectory herself* using her
reasoning + the live graph — natural/colloquial questions, wide structural variety,
and genuine **multi-step decompositions** (step 2 consumes step 1's concrete result;
e.g. busiest-venue→top-winner-there). Division of labor: **content (questions,
queries, reasoning, decomposition) is 100% hers; a harness does only faithful
execution/serialization** (byte-exact tool results via
`json.dumps(result.data(), default=str, ensure_ascii=False)`) — MCP was her
scratchpad, the driver-harness the faithful printer. Efficiency principle:
trajectories show the **efficient expert path, not fumbling** — multi-step ONLY when
the question genuinely needs decomposition, never gratuitous error-recovery.
(Tool-call efficiency noted as a future RL-reward dimension.)

**Quality discipline (batch-then-review, which caught real bugs both times):**
- Delivered in waves (35→83→130); I ran an **independent execution audit each time**
  — re-ran every Cypher against the graph; final counts **130/130** numbers
  reproduced by their own queries.
- Guards enforced: number-gated (every answer number stated AND present in executed
  results); **cross-step internal-consistency rule** (the final answer must not
  assert a number a later step contradicts); dedup vs eval/OOD on (entities+answer);
  **exclude all 6 held-out OOD types + all eval ids** (measurement integrity — so the
  frontier stays a valid generalization test).
- **Bugs caught & fixed:** (1) cross-granularity dismissal inconsistency — the
  aggregated `DISMISSED→BOWLER_TOOK_WICKET` count ≠ the ball-by-ball
  `FACED∩BOWLED∩isWicket` count (root cause: a **non-striker run-out inflating the
  aggregate**); a multi-step "bogey bowler" trajectory asserted 5 while its own
  matchup query returned 4. Fix: single-source + the consistency rule. NOTE: earlier
  we verified pre-aggregated batting *runs* == ball-by-ball; *dismissal-attribution*
  does NOT agree across granularities. (2) "bunny" idiom inverted (a bunny is the
  *batter* a bowler dismisses; possessive belongs to the bowler) → "bogey bowler".

**FINDING — structural saturation.** A single KG/domain supports only a finite number
of *meaningfully-distinct* Cypher structures — here ~**124–140**; past that, new rows
are entity-variation (same shape, new player), i.e. the low-value padding that
*re-creates* the memorization dynamic. So we deliberately **stopped at 124 distinct
(130 total, shape-repeats capped ≤4)** rather than padding to an arbitrary 300.
Quality-of-structural-coverage > volume. (Blog-worthy: bounds how much genuinely
novel supervision a KG-QA task can even provide.)

**Data inventory (frozen):** template SFT 913 · diverse SFT 130 · eval 228 ·
OOD paraphrase 89 · OOD held-out-type 96. Authoring sources:
`cricket-analytics/utils/data_gen/authored_batch{1..7}.py` + `assemble_trajectories.py`.

**Purpose:** Exp S3 will SFT (from base) on templates+diverse combined → RL
(number-gated reward) → gate on all 3 distributions, testing whether structural
breadth **transfers** to the held-out frontier (currently 0.33).

## Exp S3 — diverse-SFT (templates + 130 diverse), stage 1 (SFT) done (2026-07-03)

**Setup** (`cricket_sft.py`, log `sft3`, W&B `uu0snjdm`): Qwen3.5-9B LoRA 32, SFT
from BASE on the **combined** corpus = 913 templates + 130 diverse (`jsonl_paths` now
includes `diverse_trajectories.jsonl`) → **1043 trajectories, 2121 examples**
(tiers hard 378 / med 374 / easy 291), 2 epochs, LR get_lr. This is *S2's data +
124 diverse structures* — so S3-vs-S2 isolates the structural-breadth effect.

Pre-launch smoke passed: combined ingest clean; number-gated reward verified live in
the GRPO loop (reward/total [1.0, −0.025], `number_frac` present, checkpoint saved,
0 errors).

**SFT result:** 132 steps, loss 0.974 → **0.033** (≈ S2's 0.023 — normal 2-epoch fit,
not a collapse; healthy). Ckpts: sampler
`tinker://c4bc90dc-...:sampler_weights/final`, state `.../weights/final`.

**HELD for user go before RL** (per user request to pause at the SFT stage). Next:
optionally gate SFT-only on the 3 distributions (read-only) to see if diverse-SFT
alone moved held-out, then RL (number-gated) from the S3 ckpt → full 3-way gate vs
the current best (in-dist 0.97 / paraphrase 0.85 / held-out 0.33).

### S3 SFT-only gate (no RL yet) — 2026-07-03

Gated the S3 SFT-only sampler (`c4bc90dc...`) on all 3 distributions:

| ckpt | in-dist | paraphrase | held-out | the 4 novel-structure types |
|---|---|---|---|---|
| base | 0.54 | 0.46 | 0.17 | 0.00 |
| S2 SFT (templates) | 0.95 | 0.84 | 0.23 | 0.00 |
| SFT+RL (G2) | 0.97 | 0.85 | 0.33 | 0.00 |
| **S3 SFT-only (diverse)** | **0.991** | 0.831 | 0.312 | **0.00** |

**Diverse SFT alone ≈ prior SFT+RL** (held-out 0.31 vs 0.33) and set a new in-dist
high (0.99) — WITHOUT any RL. Per-type held-out (S3): fielder_dismissals 1.00
(base already 0.87 = schema-obvious), most_sixes_in_season **0.44→0.83** (diverse had
many ranking/superlative structures → the near-composition transferred).

**THE WALL (headline):** the **4 genuinely-novel structures — partnership_runs,
bowling_in_phase, boundary_pct_powerplay, win_pct_batting_first — remain 0.00 across
EVERY intervention** (base / pure-RL / S2 / SFT+RL / S3-diverse). High entity (0.72–1.0)
but 0 number → "confidently wrong" (fires a memorized-shaped wrong query). Training on
124 diverse structures did NOT transfer to them.

**Refined finding:** generalization here = **interpolation within the trained
structural space** (most_sixes ~ rankings we trained → transfers), NOT extrapolation to
**genuinely novel structures** (pair-at-crease, phase-filtered BOWLED, boundary-ratio,
innings-order win% — none resemble a trained shape → 0). Diversity lifts the near
neighbours; it does not teach the model to *compose an unseen structure*. That wall
looks fundamental to this 9B + approach (would need those structures' own
demonstrations — which defeats the held-out test — or a stronger base).

**Implication for RL:** in-dist already 0.99; the 4 zeros won't move under
same-distribution RL (G2 showed RL only helped the near-composition most_sixes). So RL
from S3 is expected **marginal**. Decision pending: (a) lean RL to confirm + complete
the 4-cell matrix (cheap, ~$3–6, fits balance); or (b) declare the frontier finding and
write up — the "diversity interpolates, doesn't extrapolate to novel structures" result
is clean and publishable as-is.

### S3 SFT+RL (lean RL, number-gated) — COMPLETED MATRIX (2026-07-04)

Lean RL from S3 ckpt (LR 1e-5, group 4×4, 30 steps ≈ 480 rollouts, ~$-cheap). Train
reward flat 0.75→0.75 (in-dist near-ceiling). Ckpt sampler `802c2ff1...`.

**FINAL MATRIX (ALL correct):**

| ckpt | in-dist | paraphrase | held-out |
|---|---|---|---|
| base | 0.54 | 0.46 | 0.17 |
| S2 SFT (templates) | 0.95 | 0.84 | 0.23 |
| SFT+RL (G2) | 0.97 | 0.85 | 0.33 |
| S3 SFT-only (diverse) | **0.99** | 0.83 | 0.31 |
| S3 SFT+RL | 0.93 | 0.88 | 0.32 |

RL-on-diverse = a **redistribution, not a net gain**: held-out flat (0.31→0.32),
in-dist REGRESSED (0.99→0.93), most_sixes dropped (0.83→0.67) — but
**boundary_pct_powerplay 0.00→0.27** (a type flat-zero across 5 prior checkpoints).
Best all-round checkpoint = **S3 SFT-only** (0.99/0.83/0.31).

**Per-type frontier (S3+RL):** partnership_runs 0.00 · bowling_in_phase 0.00 ·
**boundary_pct_powerplay 0.27** · win_pct_batting_first 0.00 · fielder_dismissals 1.00
· most_sixes 0.67.

**INSPECTED boundary_pct (verified real, not artifact):** the RL'd model genuinely
composes the boundary-ratio structure — correct reasoning + query shape
`sum(CASE WHEN batterRuns IN [4,6])*100/sum(batterRuns)`. But fragile: on "S Dhawan"
it used non-existent `d.overNumber` (phase filter must traverse the `Over` node) →
0/0 → div-by-zero → confidently concluded "Dhawan scored 0 powerplay runs" (no cricket
sanity-check). Real composition, unreliable execution → 4/15.

**REFINED FINDING (the payoff — supersedes "interpolate not extrapolate"):** the
generalization boundary is **compositional recombination of TRAINED sub-elements, but
not invention of an UNSEEN primitive.**

| type | needs | in train? | outcome |
|---|---|---|---|
| boundary_pct | FACED-phase + boundary-ratio | both seen separately | RL COMPOSED → 0.27 |
| bowling_in_phase | phase on BOWLED | never (only batting phases) | 0.00 |
| partnership_runs | pair-at-crease (FACED+NON_STRIKER) | never | 0.00 |
| win_pct_batting_first | innings-order-conditional win% | never | 0.00 |

RL extended composition to a **recombination of known parts** (FACED-phase + ratio),
but neither SFT nor RL produces a structure needing a **never-seen element**
(BOWLED-phase, crease-pairing, innings-order). Prediction "all 4 stay 0" was WRONG
(logged); RL under-called twice (G2 held-out moved, now boundary_pct). Digging in
(inspection) — not trusting the number — was essential.

**PROJECT COMPLETE — publishable arc.** Ladder of generalization on a real KG-QA task:
new entities (0.99) → new wording (0.88) → recombined-known-structure (boundary_pct
0.27) → genuinely-novel primitive (0.00, a hard wall). SFT provides breadth; RL
recombines trained parts; neither invents an unseen primitive. Next: (a) WRITE UP
(matrix + per-type frontier + the inspection are figure-ready, claim→evidence→figure
like [[project_legal_rl_blog]]); (b) optional: cross-check any early figures vs W&B.
Best ckpt for a product = S3 SFT-only `c4bc90dc...`. Nothing running.
