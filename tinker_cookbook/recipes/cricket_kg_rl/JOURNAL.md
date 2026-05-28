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
