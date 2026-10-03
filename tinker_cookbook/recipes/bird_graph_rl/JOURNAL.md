# bird_graph_rl — experiment journal (append-only)

## 2026-09-20 — E0: profile + export `codebase_community` via a one-off Lambda

**Why:** the source SQLite file lives in object storage and must not be staged on the
laptop. Row counts, FK orphan rates and NULL rates are needed before the graph model is
final (GRAPH_MODEL.md §8).

**Preflight (written before the function exists):**
1. *Timestamped progress per unit of work?* Yes — one log line per table / per check, with
   elapsed seconds, to CloudWatch.
2. *Results written incrementally?* Profile: single small JSON (seconds of work, nothing to
   lose). Export: one CSV object per table, uploaded as each finishes.
3. *Working memory growth / peak vs limit?* SQLite file (~481 MB) goes to /tmp (ephemeral
   storage, 4 GB), not RAM. Rows are streamed with a cursor. Tag name→id map is the only
   in-memory structure (small). Memory set to 3008 MB.
4. *If killed at 80%?* Profile: rerun (cheap). Export: finished tables survive in storage;
   rerun is idempotent (overwrites same keys).

**Cost:** Lambda 3008 MB x <=15 min hard timeout = at most ~2,650 GB-s against a
400,000 GB-s monthly free tier. IAM role: free. Hard timeout is the watchdog.
**Blast radius:** account concurrency limit is 10 and is shared with production functions;
this job holds 1 slot for a few minutes.
**Teardown:** delete function, role and log group when the CSVs are verified.

### E0 results — 2026-09-20 (same day)

**Profile (Lambda, 10.1 s billed, 629 MB peak):** users 40,325 · posts 91,966 (42,912 Q /
47,755 A / 1,299 other) · comments 174,285 · votes 38,930 · postHistory 303,155 ·
badges 79,851 (153 distinct names) · tags 1,032 · postLinks 11,102. An empty `postTags`
table exists in the file but not in BIRD's published DDL; ignored.
- `votes.UserId` is NULL for 35,505 / 38,930 votes (91%) → the Vote-as-node decision was
  necessary, not stylistic.
- FK orphans are tiny (comments→posts 36, postHistory→posts 41, posts.ParentId 6,
  postLinks 1+3, AcceptedAnswerId 1, ExcerptPostId 1). Nodes kept, relationships dropped.
- Every tag parsed from `posts.Tags` exists in `tags` (0 unknown, 117,633 post–tag pairs);
  19 tags' declared `Count` differs from the parsed count → counters kept verbatim.
- All 12 datetime columns parse cleanly; fractional part is always `.0`.
- `users.DisplayName` is NOT unique: 35,644 distinct over 40,325 users. No uniqueness
  constraint on it, and gold answers keyed on a display name may span several users.
- Text volume: postHistory.Text 199M chars (max 31,268), posts.Body 104M (max 38,847),
  comments.Text 40M (max 667), titles max 154.

**Export (Lambda, 25.0 s billed, 859 MB peak):** 22 CSVs, 416 MB, 649,846 node rows and
1,380,394 relationship rows. Each relationship count equals non-NULL FK minus orphans.

**Load — two things failed first, both caught before any data was written:**
1. `neo4j-admin database import` from `s3://` → `No storage system found for scheme: s3`.
   The Community build advertises S3 in `--help` but ships no provider. Switched to
   `LOAD CSV` over presigned HTTPS.
2. Presigned URL on the global S3 endpoint → HTTP 307 (new regional bucket); `LOAD CSV`
   does not follow it. Regional endpoint → 206. Fixed in the loader.
Also set `db.import.csv.legacy_quote_escaping=false` (restart required). A `brew services
restart` raced (new process saw the old PID and exited); stop-then-start fixed it.

**Load result:** 342.8 s total; postHistory nodes dominate (204.6 s). **All 7 node labels
and all 14 relationship types match the manifest exactly** (649,846 / 1,380,394).
NULL handling verified (users with age 8,318; postHistory with comment 121,971 — both equal
profile). Types verified: LOCAL DATETIME, DATE, INTEGER. 22,362 posts contain backslashes and
max body length is 38,847 = source, so quoting is intact.
Schema: 8 node + 2 relationship uniqueness constraints, 14 range + 2 text indexes, all ONLINE;
sample query plans with NodeIndexSeek.

**Not done / open:** (a) no SQL-vs-Cypher answer cross-check yet — the graph matches the
source *structurally*; gold-answer equivalence is untested. (b) Final store size unmeasured:
`db.checkpoint()` is not available in Community, 947 MB still sits in transaction logs.
(c) Agent safety settings (timeout, memory cap, read-only) not yet applied.
**Teardown:** Lambda, IAM role and log group deleted and verified gone. CSVs + manifest +
profile remain in object storage (416 MB) as the reproducible source; reload takes ~6 min.

## 2026-09-20 (night) — E0b: dump taken; gold-SQL quality checked with evidence

**Dump:** `neo4j-admin database dump` (DB stopped ~1 min) → 418 MB → object storage under
`codebase_community/dump/`; local copy removed; DB restarted and re-verified at
649,846 / 1,380,394. Restore = `neo4j-admin database load`, no pipeline rerun needed.
Store on disk: 614 MB + 947 MB transaction logs.

**Is BIRD's gold SQL wrong? Mixed — measured, not assumed.** For each contested mini-dev
question I ran two Cypher queries on the graph: (A) the question's plain meaning,
(B) a faithful reproduction of the gold SQL's join path. *Caveat: (B) is my Cypher
re-expression; the gold SQL itself has not yet been executed on SQLite.*

| question | mini-dev gold SQL does | A vs B on this data | Nov-2025 corrected release |
|---|---|---|---|
| post by slashnick with most answers | joins via postHistory (editors), not ownership | same (post 351) | **fixed** → `OwnerUserId` |
| most valuable post in 2010 | filters on the *user's* creation year | same (post 1595) | date filter **fixed**; still returns `OwnerUserId` where the question asks for the post id |
| title mentions "variance", bounty 50 | `LIKE` (case-insensitive) | same (2 rows) | not checked |
| view-count difference Mornington − Amos | sums ViewCount once per *edit-history row* | **differ: −497 vs −1491** (6 history rows over 4 posts) | not retrieved (API error) |
| % of Community's posts using R | joins `tags.ExcerptPostId` to history rows | **differ: 0/211 vs 1/510** | **fixed** → owner join + `Tags LIKE '%<r>%'` |
| Harvey Motulsky vs Noah Snyder popularity | sums ViewCount per edit-history row | same winner, totals 23,065 vs 185,078 | **NOT fixed** (still via postHistory) |

**Earlier claim softened by this evidence:** I had said several gold SQLs "look wrong". The
logic *is* wrong in those, but on 4 of 6 the answer coincides anyway. The real exposure is
numeric questions where row multiplication changes the number.
**Decision proposed:** take gold from the Nov-2025 corrected release (`birdsql/bird_sql_dev_20251106`),
not mini-dev; audit every codebase_community item A-vs-B; keep a per-question flag
`gold_matches_plain_meaning`.

## 2026-09-21 — E1: execute BIRD gold SQL on SQLite → reference answers

**Why:** the reward needs execution-verified reference answers, and E0b showed some gold SQL
is logically wrong. Get the real SQLite results (not my Cypher re-expressions) for every
`codebase_community` question in BIRD's Nov-2025 corrected release, plus the mini-dev SQL
for the overlapping questions, and flag fragile items (errors, empty results, `LIMIT 1` ties,
corrected-vs-mini-dev answer changes).

**Preflight:** (1) progress: one log line per 25 questions. (2) incremental: single results
JSON; whole job is seconds-to-minutes, rerun is cheap. (3) memory: result rows capped at
200 per question, SQLite file on /tmp not RAM. (4) killed at 80%: nothing lost but time.
Per-query guard: SQLite progress handler aborts any statement after 20 s.
**Cost:** same temporary Lambda shape as E0 (3008 MB, 15 min cap), free tier. Same scoped
role, recreated; deleted again after. Holds 1 of the account's 10 concurrency slots briefly.

### E1 results — 2026-09-21

Lambda 40.1 s billed, 637 MB peak. **Corrected release: 186 questions, 0 errors, 0 empty**,
11 return >200 rows (max 20,198), 16 `LIMIT 1` queries probed → 1 tied (Q669, top two sort
keys both 2010-08-13). Slowest query 15.2 s (under the 20 s guard). Mini-dev: 49 questions,
0 errors, 2 tied.
**Mini-dev vs corrected (49 overlapping): SQL changed on 15, executed ANSWER changed on 8**
(Q581 Paul→naught101, Q637, Q639 0.196→0.0, Q640 −1491→−497, Q683 7.24→51.17, Q694, Q710
2888→10997, Q716 1.33→4.87). So mini-dev gold was materially wrong on 16% of this DB.
**First true SQL-vs-graph check: 5/5 match** — Q640 mini (−1491) and corrected (−497),
Q633 (351), Q639 (0.0), Q669 ('2010-08-13'). This retires the E0b caveat: my Cypher
re-expressions of the gold logic were faithful.
Outputs in object storage under `gold/`. Lambda, role, log group deleted and verified gone.
Docs added: DATA_HANDOFF.md (public-safe), LOCAL_RESOURCES.md (gitignored).

## 2026-09-21 — guardrails set (blocking item cleared)

`db.transaction.timeout=120s`, `db.memory.transaction.max=2g` written to `neo4j.conf`;
verified live as `2m` / `2.00GiB`; graph intact at 649,846 / 1,380,394 after restart.
**Corrected claim:** I previously called these "dynamic settings" because `SHOW SETTINGS`
reports `isDynamic: true`. The docs say runtime changes via `dbms.setConfigValue` are
**Enterprise-only**, and the procedure does not exist on this build — so Community requires
the config file and a restart. Upside: the change persists.
Read-only is still unenforced at the server (RBAC is Enterprise); the query tool must use
read transactions. Open: gold Cypher for the 186 questions · reward function ·
training-question strategy · trainer/platform.

## 2026-09-21 — how much structure do the 186 questions actually cover?

Measured a structural signature per gold query (tables touched, aggregations, and presence of
subquery / GROUP BY / HAVING / ORDER-BY-LIMIT / CASE / CAST / DISTINCT / LIKE / date / IS NULL):

| metric | value |
|---|---|
| questions | 186 |
| **distinct query structures** | **64** |
| structures appearing exactly once | 42 |
| tables touched per query | 1 → 57 · 2 → 116 · 3 → 13 (never more) |
| queries with no aggregation at all | 90 |
| most common single structure | 2 tables, no aggregation, no features (34 questions) |

**Reading:** the benchmark exercises a thin slice of this graph — at most a 2–3 hop join, half
the questions with no aggregation, and nothing that traverses `LINKS_TO` chains or paths like
User→PostHistory→Post→Tag. Prior work on a different KG (cricket, 2026-07) found that domain
saturating at ~124–140 distinct structures, so a single schema has roughly 2× headroom in
structural space — **not** the order of magnitude that RL volume needs.
**Implication:** "more questions" on one schema is the wrong axis; distinct *structures* is the
axis, and one schema caps out. See the E2 preflight below.

## 2026-09-21 — E2 preflight: zero-shot baseline (`baseline_eval.py`, written, NOT yet run)

Scores model-returned rows against the execution-verified reference answers, so no gold Cypher
is required. Tool is read-only: write-keyword rejection plus `execute_read`, since the server
has no RBAC. Metrics per question: exact row-set match, value-set match, and reference-covered
(looser). Reports by difficulty (151 simple / 30 moderate / 5 challenging).

**Rule-7 preflight, answered before the machine exists:**
1. *Timestamped progress per unit of work?* One line per completed question with elapsed seconds.
2. *Results to disk incrementally?* One JSON line appended per question to `log_path`, not one
   write at the end.
3. *Does working memory grow?* Per-question transcripts are held only for the question in flight;
   tool results are truncated to 4 KB before entering the conversation and rows capped at 50.
   Bounded by `concurrency` (default 16), not by the question count.
4. *If killed at 80%?* Every finished question survives in the JSONL; rerun skips them.

**Cost shape:** 186 questions × up to 6 turns × 1024 max tokens, temperature 0. Billed by Tinker
sampling; no GPU rental, no pod, so no idle watchdog is needed — the turn cap is the bound.
**Not yet decided (blocking the run):** which model. Tinker currently lists 31 models; smaller
candidates are Qwen3.5-4B, Qwen3.5-9B, Qwen3-8B, gpt-oss-20b, Qwen3.6-27B, Qwen3.8-27B.

## 2026-09-21 — E2 opening balance (before any sampling)

- **Opening balance: $131.36** (Tinker console → Billing → Balance, screenshot from the owner,
  2026-09-21). A dedicated API key for this project lives in the repo `.env`.
- The SDK has **no balance endpoint**; `get_billing_usage` returns hourly token counts only, no
  dollars, lagging up to a few hours. Opening token snapshot for this org over the prior 14 days:
  **0 sampling tokens, 0 training tokens**, storage only (6,560 GB-hours; ~19.7 GB stored now,
  i.e. ~$2/month at $0.10/GB-month — old checkpoints, left untouched).
- Prices for Qwen/Qwen3.8-27B (docs, 2026-09-21): prefill $1.86/M, cached prefill $0.372/M,
  sample $5.595/M. An earlier estimate priced every token at the sample rate and overstated cost.
- Cost is tracked three ways: live token meter in the harness (upper bound, prompt at uncached
  rate), billing usage filtered by the run's session metadata (exact tokens, hours later),
  and the console balance at the end.

## 2026-09-21 — E2 harness rebuilt on upstream patterns; pre-run validation (free)

The first draft copied its structure from the June-era cricket harness. Rebuilt against the
**current upstream** code instead: `recipes/search_tool/offline_eval.py` (upstream's own offline
tool-agent eval) uses the same building blocks, and `rl/rollout_runner.run_rollout` (added
upstream 2026-07) is now the single rollout loop — `do_single_rollout` just delegates to it.
Adopted from upstream: `run_rollout` with `RolloutLimits` (per-episode `max_sampled_tokens`
as a cost guard), `recipe_user_metadata` session tagging, and **no client-side sampling
timeouts** (repo CLAUDE.md pitfall 2).

**Caught before spending:** the repo `.env` `NEO4J_URI` points at an old cloud host whose DNS
no longer resolves. The harness now reads dedicated `BIRD_NEO4J_*` variables (local instance)
and calls `verify_connectivity()` before any sampling.

**Scorer validated offline (no Tinker calls):** known-correct Cypher for q640, q633, q639,
q669 → all scored correct (incl. a `neo4j.time.Date` vs `'2010-08-13'` string); the known-wrong
edit-history version of q640 (−1491) → scored 0; large-result q532 (4,430 rows vs a 200-row
capped reference) → correct via count + containment.
**Read-only verified at the server:** a write inside a read transaction is rejected with
`Neo.ClientError.Statement.AccessMode`. The keyword check is a second layer and now strips string
literals first (a title search for 'data set' was previously being blocked — my bug).

**Run config (smoke, then full):** Qwen/Qwen3.8-27B, renderer = model_info default
`qwen3_8_xhigh_reasoning`, temperature 1.0 (the RL sampling temperature, so this is the starting
policy's expected reward; single sample ⇒ ±~3.7 pp SE at n=186), max 8 turns, 8,192 tokens per
turn, 16,384 sampled tokens per question, 56K trajectory cap, concurrency 16.
**Watchdog:** harness stops starting new questions once its upper-bound estimate crosses
`budget_usd` (smoke: $5). Per-question worst case ≈ 16K sampled × $5.595/M + prompt ≈ $0.2.

### E2 smoke result — 10 questions (all "simple"), Qwen3.8-27B, 2026-09-21 23:54

strict 0.50 · lenient 0.60 · no_query 0 · mean 2.9 turns · mean 4,781 prompt + 1,132 sampled
tokens · **upper-bound cost $0.15 total (~$0.015/question)**. 63 s wall clock.
Every failure inspected — they are not all model errors:

| q | cause | who is "wrong" |
|---|---|---|
| 534 | returned name **and** views; question asks for name | model (format) — lenient passes |
| 532 | returned all 4,430 names `collect()`-ed into one list row | model (format) |
| 531 | returned both users + reputations instead of just the higher one | model (reasoning) |
| 533 | 5,146 vs 4,941: counted accesses *on* 2014-09-01; gold uses `date(x) > '2014-09-01'` — difference is exactly the 205 users who last accessed that day (verified) | ambiguous boundary |
| 538 | returned the 12 non-null titles; gold returns 121 rows, 109 of them NULL (answers have no title) — verified 12 = non-null count | gold quirk; model arguably right |

So strict execution accuracy is harsh on output **shape**, which is cheap to learn and a
clean RL signal, and it also inherits gold quirks. Primary metric stays strict (BIRD-faithful);
lenient is reported alongside. Rescoring later is possible without resampling because every
`final_query` is stored and the graph is static.
Full run launched: 186 questions, `budget_usd=15`.

### E2 RESULT — full zero-shot baseline, Qwen/Qwen3.8-27B, 186 questions (2026-09-21 23:56–23:59)

| tier | n | strict | lenient | turns |
|---|---|---|---|---|
| simple | 151 | 0.675 | 0.722 | 4.16 |
| moderate | 30 | 0.367 | 0.467 | 4.77 |
| challenging | 5 | 0.000 | 0.600 | 6.00 |
| **ALL** | **186** | **0.608** | **0.677** | 4.31 |

no_query 0 (the model always uses the tool) · 172 completed, 14 hit the 8-turn cap ·
42 questions had ≥1 Cypher error along the way · 172 s wall clock at concurrency 16.
**Tokens:** 1,532,175 prompt + 209,682 sampled → **upper-bound $4.02** (prompt priced uncached;
true cost lower because repeated prefixes hit the prefill cache). Smoke run added $0.15.
Budget stop never triggered.

**73 failures by cause (automatic, from stored rows):**
27 same row count but different values · 25 different row count · 13 right values in the wrong
shape (extra columns) · 8 many rows collapsed into one (`collect()`).
So ~21 of 73 (29%) are *shape* errors — the cheapest thing RL can fix; the other ~52 are
semantic (wrong filter, boundary, join, aggregation — and some gold quirks, see smoke table).

**Reading:** a strong 27B model already gets 61% zero-shot; the headroom is moderate (0.37) and
challenging (0/5 strict). n=5 challenging is too small to conclude anything alone. Single sample
at T=1.0 ⇒ ±~3.6 pp standard error on the overall number.
**Open:** reconcile the $4.02 estimate against (a) console balance vs the $131.36 opening and
(b) `get_billing_usage` filtered on this run's session metadata once the few-hour lag passes.

## 2026-09-22 — E2 replicated on Fireworks: no framework effect; the noise floor is the finding

The Fireworks session ran **this repo's harness unchanged** — importing `baseline_eval` and
patching only the sampling client to a Fireworks serverless sampler of the same checkpoint
(Qwen/Qwen3.8-27B). It refuses to start unless the harness blob equals `6390bc9`, which I
verified is exactly `baseline_eval.py` at `ed9e7f7`. So prompt, renderer, tool, limits, scorer
and output schema are identical byte for byte. Its files: `~/bird_rl_runs/e2fw_full_qwen3_8_27b/`.

**Recomputed here from both results files (not taken from the report):**

| | Tinker | Fireworks |
|---|---|---|
| strict | 0.608 | 0.608 |
| lenient | 0.677 | 0.656 |

Paired strict: both right 92 · both wrong 52 · **Tinker-only 21 · Fireworks-only 21** · McNemar
exact p = 1.00 · agreement 0.774. Paired lenient: 18 vs 14, p = 0.60.
Per-tier differences (simple .675/.636, moderate .367/.500, challenging 0/5 vs 2/5) are within
single-sample noise at these n.

**What this actually tells us:**
1. **No detectable framework effect** — same model, same code, same score.
2. **The noise floor is large: 42 of 186 questions (22.6%) flip between two single samples at
   T=1.0.** Any RL gain measured with one sample per question must clear that. Checkpoint
   comparisons need several samples per question and paired tests, not one-shot accuracy.
3. **134/186 (72%) are solved in at least one of two samples** vs 0.608 for one sample. The 42
   flippers are exactly where GRPO-style RL has signal (mixed outcomes within a group); the 52
   never-solved are where it has none unless sampling finds a success.
4. Pooled over 372 samples the baseline is 0.608 (SE ≈ 2.5 pp).

**Cost:** Fireworks $3.12 (billed tokens equal the harness meter exactly; 47% of prompt tokens
cached). Tinker $2.33 by console. The gap is most likely prefix-cache hit rate (my arithmetic
implies roughly 75–78% cached on Tinker) — **unconfirmed**: Tinker billing usage for
18:00–20:00 UTC had no sampling events yet when queried (documented lag of a few hours).

## 2026-10-03 — partial-credit reward measured (free, no sampling): it helps less than I claimed

`reward.py` grades a rollout by **row-level F1** between the rows its final Cypher returns and
the reference rows, returning exactly 1.0 only when the strict scorer would. No judge, no
vendor, deterministic. Deliberately excludes any "mentioned the right value" term — an earlier
project on another graph found that teaches entity-echoing without computing.

Measured by re-executing every stored `final_query` from both baseline runs (372 queries) against
the live graph. Nothing was sampled; this cost nothing.

| | Tinker | Fireworks |
|---|---|---|
| strict (binary) | 0.608 | 0.608 |
| mean partial credit | 0.639 | 0.642 |

**The number that matters, and it is not flattering to my proposal:**

| | value |
|---|---|
| never-solved set (strict 0 in both runs) | 52 |
| of those, non-zero partial credit in at least one run | **13 (25%)** |
| of those, still exactly 0 | **39** |
| questions with reward spread across the 2 samples, binary | 42 / 186 |
| questions with reward spread across the 2 samples, partial credit | **47 / 186** |

**Reading.** Partial credit converts 5 more questions from flat to graded, and lifts mean
reward by 0.03. That is a real but small gain, and it does **not** solve the flat-reward
problem: 39 of the 52 hardest questions return rows with *zero* row overlap with the reference.
Those are not near misses — the query is semantically wrong, so there is nothing partial to
credit. I previously argued partial credit was the cheap fix that made a learned judge
unnecessary for shaping. On this evidence that argument is too strong, and the judge arm has a
real gap to aim at. Partial credit is still worth adopting because it is free and strictly
better than binary, but it is not the answer to the dead-group problem.

**Important caveat on the "52".** It was measured at k=2. GRPO will use a group of 8, where more
questions will produce mixed outcomes, so 52 is an upper bound on dead questions, not an
estimate. This should be re-measured at the k we settle on before designing around it.

## 2026-10-03 (later) — exact references, plan frozen for review, data generation started

- **Exact reference rows.** The 11 questions whose stored rows were capped at 200 now have their
  complete result sets (60,527 rows; `etl/lambda_full_refs.py`, one-off Lambda, deleted after).
  Every re-executed row count equalled the stored `n_rows`. `reward.load_references_exact`
  merges them, so row-level F1 is exact for all 186 and the approximate branch is dead code.
  Re-measured: mean partial credit 0.640 (Tinker run) / 0.643 (Fireworks run); every structural
  count unchanged (52 never solved, 13 rescued, 39 at zero, spread 42 → 47). The Fireworks
  session reproduced the counts independently and the same 13 question ids.
  *Not yet done:* re-executing all 186 gold SQLs and diffing against the stored reference, as a
  drift check on the gold itself (requested by the Fireworks session; cheap; open).
- **Hard stop is 2026-10-17**, not the credit expiry. `PLAN.md` holds tasks, owners, dates and
  the cut order. The owner's objective, verbatim in spirit: smaller open model → baseline →
  post-train → measure the gain → publish.
- **Data generation (critical path)** is specified in `datagen/SPEC.md`: query-first, structures
  enumerated and split *by structure* so a held-out-structure test exists, generator forbidden
  from reading the evaluation set. Handed to Codex (`gpt-6.1-sol`) running in this repo.
- **Research dispatched to sub-agents, official sources only:** (a) can the open-weights
  decision model be served on rented serverless GPUs, and how; (b) which Tinker-served model is
  the strongest frontier reference by provider-reported agentic results. The live Tinker list
  today is unchanged from 2026-09-21 (31 models, 19 base).

## 2026-10-03 — research (official sources): can the open decision model be self-hosted? (T9)

Sub-agent report, sources limited to the model's Hugging Face repo files, vLLM and transformers
source, and docs.runpod.io. Subject: `perplexity-ai/pplx-decider-v1-27b`.

- **Deployable, but only as a custom container running the repo's own PyTorch code — not vLLM.**
  `config.json` declares `Qwen3_5Model` (backbone only); the checkpoint has **no `lm_head`**, and
  the decision head is a separate `readout.safetensors` (a 255-way linear layer over the last
  hidden state, with a calibrated temperature). vLLM does not register that architecture string
  and would fall back to treating it as an embedding model.
- The repo ships its own inference package and a FastAPI server (`POST /v1/systemone`), with one
  in-flight request per worker (returns HTTP 529 when busy).
- **Input cap is 8,192 tokens in the shipped code** (`prepare(..., max_length=8192)`, raises
  rather than truncating). An earlier note of mine repeated "250k context" from a non-official
  summary; the official inference code does not support that claim. Corrected here.
- Weights are 48.59 GiB BF16, single device only → an 80 GB card. Serverless price for an
  A100 80 GB is $2.72/hr per the live catalogue (the $1.39/hr I quoted earlier was the on-demand
  pod figure, not serverless). No official quantised variant exists.
- Unverified from official sources: cold-start time for ~49 GiB, any serverless image-size limit,
  peak working memory, and the hosted API's price.
- The same model is also offered by its publisher as a hosted endpoint with the same semantics.

**Assessment for T9 (stretch).** Self-hosting is roughly a day of engineering (custom ~50 GiB
image, health-check patch, concurrency 1) for a task that is already optional under a two-week
deadline. If the judge experiment runs, the publisher's hosted endpoint of the same open weights
gives identical semantics with no infrastructure; self-host only if the hosting itself is wanted
as content. The 8,192-token cap is compatible with the planned judge input (≤30 rows, ≤3,000 chars).

## 2026-10-03 — research (official sources): the model we baselined is itself near the frontier

Sub-agent report from providers' own model cards, release notes and the Tinker models page.
Release dates of Tinker-served candidates: GLM-5.3 (API 2026-08-18, weights ~08-27) ·
**Qwen3.8-27B (2026-08-14)** · Inkling-Small (07-30) · Inkling (07-15) · Nemotron-3-Ultra (06-04) ·
Kimi-K2.6 (04-20) · Qwen3.5-397B (02-16) · DeepSeek-V3.1 (**2025**-08-21).
- DeepSeek-V3.1, which I had proposed as the frontier reference, is the oldest model on the list
  by a year. The owner's objection was correct; proposal withdrawn.
- By provider-reported agentic numbers the strongest three are GLM-5.3, **Qwen3.8-27B** and
  Kimi-K2.6. Providers report on different benchmarks under different harnesses, so no
  cross-vendor ranking is possible from official sources; the only comparable measurement is
  running candidates through our own harness.
- **Consequence.** Qwen3.8-27B is not "a smaller model below the frontier"; it is one of the
  frontier references. Our 0.608 is therefore better read as the *reference* number.

**Budget evidence pointing the same way (Fireworks agent, measured + estimated):** sampling cost
≈ $0.016 per rollout on the 27B; a 3,200-rollout RL run is roughly $93–173 including training
tokens, against ~$148 of Fireworks credit and ~$129 of Tinker credit. One RL run on the 27B would
consume nearly all of either balance, leaving nothing for iteration or evaluation.

**Proposal to the owner (not yet decided):** student = a genuinely small model (Qwen3.5-9B or
Qwen3.5-4B); references = Qwen3.8-27B at 0.608 (already measured on both platforms) and
optionally GLM-5.3 as the ceiling. This matches the stated objective and makes RL affordable.

### E3 preflight — zero-shot baselines of the small candidates (same harness, same 186)
Qwen/Qwen3.5-9B and Qwen/Qwen3.5-4B, default renderer `qwen3_5`, T=1.0, 8 turns, identical caps.
(1) progress: one line per question. (2) incremental JSONL per question, rerun skips finished.
(3) memory: per-question only. (4) killed at 80%: finished questions survive.
Cost estimate from the 27B run's billed $2.33 scaled by published prices: ≈$0.85 (9B), ≈$0.45
(4B) if token use is similar; harness stop at `budget_usd=5` each. Opening balance: $129.03 was
the last console reading (2026-09-22); the SDK exposes no balance endpoint.

### E3 RESULT — zero-shot baselines of the small candidates (2026-10-03)

| model | strict | lenient | simple | moderate | challenging | turns | est. cost (upper) |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B (reference, E2) | 0.608 | 0.677 | 0.675 | 0.367 | 0/5 | 4.31 | $4.02 |
| **Qwen3.5-9B** | **0.425** | 0.591 | 0.483 | 0.167 | 1/5 | 3.88 | $1.00 |
| Qwen3.5-4B | 0.376 | 0.489 | 0.430 | 0.167 | 0/5 | 5.03 | $0.70 |

Both always use the tool (no_query 0). **There is real headroom: 18 points (9B) and 23 points
(4B) below the 27B reference.** The 9B's lenient score is 17 points above its strict score, the
widest such gap of the three: many of its failures have the right values in the wrong shape,
which is the cheapest kind of error for RL to remove. Single sample each, so ±~3.6 points.

**Platform constraint (Fireworks agent, from Fireworks' registry and docs, ledger F18–F21):** the
4B is not trainable on Fireworks at all; the 9B is trainable only on dedicated hourly GPUs
(about $39/hour for trainer plus sampler), not per token. On Tinker both are per-token.

**Owner direction (2026-10-03):** park the decision-model judge entirely; too many variables.
Get to a first milestone, then decide what follows.
**Proposed first milestone:** Qwen3.5-9B, 0.425 → RL with the verifiable partial-credit reward on
Tinker → measured gain toward 0.608, with the pre-registered bar below.

**Pre-registered success bar (proposed by the Fireworks agent, counter-signed here before any
training):** primary metric strict on the 186, per-question mean over k samples, after minus
before, paired bootstrap over questions (10,000 resamples, 95% interval). A gain is claimed only
if the interval's lower bound is above 0 **and** the point estimate is ≥ 5 points; otherwise
"no detectable gain". Headline: fraction of the gap to the reference closed. Forgetting guard:
the simple tier must not fall by more than 3 points. Checkpoint chosen on generated
`heldout_instance` data and evaluated once on the 186. Held-out structures reported separately
as novel-combination and novel-component, descriptive, no bar.

## 2026-10-03 — T4 built: RL environment and training entry point (no sampling yet)

`rl_env.py` follows upstream's `recipes/search_tool/search_env.py`: one group builder per
question, `group_size` rollouts each, every rollout built by `build_agent_tool_env`. It imports
the system prompt, tool and caps from `baseline_eval.py` and the reward from `reward.py`, so
training and evaluation share one definition of the task. Each rollout gets its own tool instance
(the tool records that rollout's queries); the database driver is one per process. Parse-failure
and context-overflow rewards are set to 0 so the reward stays on [0, 1].
`train.py` mirrors `recipes/search_tool/train.py`; every `rl.train.Config` field it sets was
checked to exist in the merged upstream code.

**Offline validation (free):** 40 of 40 sampled generated instances score exactly 1.0 when their
own query is replayed through the RL reward; wrong query → 0; no query → 0; the environment
builds and renders an 883-token initial prompt.

**Corrected definition (Fireworks agent, ledger F28):** "hit the turn cap" was reported under
two definitions. Cut off by the cap (`stop_reason == max_turns`): 14 / 36 / 70 for the 27B / 9B /
4B. Used all eight turns: 22 / 39 / 72. The first is the one that means the cap cost an answer
and is the one to publish; my E3 note used the second.

**Interface notes from Codex's interim output (not yet reviewed in full):** queries are
parameterised (`$anchor`) and rows are dicts, so a small adapter is needed to produce the
training file; and at least some enumerated structures read unnaturally as questions (e.g.
counting user–badge pairs that share a badge with a given user), so stage B needs a naturalness
filter rather than a question for every instance.

**Proposed first-run configuration (to be confirmed by a two-update smoke run):** Qwen3.5-9B,
recommended renderer, LoRA rank 32, `importance_sampling` loss, no KL penalty, learning rate
1e-5 (the value an earlier RL project in this repo found workable; to be re-checked against the
cookbook's guidance), 16 groups × 8 rollouts, constant-reward groups removed.
**Blocked on:** natural-language questions for generated instances (stage B), and the owner's
confirmation of the student model. The smoke run is billed and creates a checkpoint, so it waits.

## 2026-10-03 — the reward is blind to the student's largest failure class (verified)

The Fireworks agent applied the pinned reward to the 9B baseline's stored queries; I reproduced
it: mean partial credit 0.452 vs strict 0.425; **of 107 failures, 9 get any credit and 98 get
exactly 0; of the 31 "right values, wrong shape" failures, 0 get any credit** (an extra column
means no whole row matches). I had written that shape errors were "the cheapest kind of error
for RL to remove". That holds only if some rollouts in a group already return the right shape;
the reward itself gives a wrong-shape answer nothing. Not changing the reward on this evidence —
a tier for "a subset of columns matches" invites wide-row farming — but the smoke run must
report the fraction of groups removed as constant and per-group reward spread.

**Decisions taken before any checkpoint exists:**
- `train_unembed=False` (SDK default is True; `rl.train` does not expose it, so `train.py` applies
  it where the training client is created). Reason: per the Fireworks agent's reading of that
  platform's docs, adapters for this model family are accepted there only without an unembedding
  adapter, so this keeps a Tinker-trained adapter deployable elsewhere. Effect on task performance
  is unmeasured.
- Database concurrency capped at 24 connections in the driver, with a long acquisition wait, so
  a 128-rollout batch queues for the local database instead of producing timeout errors that
  would reach the model and alter rewards.
- `env_file` is now a CLI field.
- Steps will be set from budget (`max_steps`), not dataset size; checkpoint selection happens
  after the run on a fixed generated set of ≥200, not on the 64-question in-loop monitor.

## 2026-10-03 — first read of the generated data: not usable as is, and two causes are my spec

Codex's interim output: 5,590 verified instances; 60 individually written pilot questions.
Reading the pilot beside the queries (free, no sampling):
- **Invented vocabulary.** Questions say "members", "standing points", "contributions",
  "remarks". My spec forbade "labels, relationship types or property names" in questions; I
  meant query syntax, and wrote a rule that also banned the ordinary words *user*, *post*,
  *reputation*. Evaluation questions use those ordinary words. **My error.**
- **Alias instructions.** Questions end "Return the total in `value`". My spec said a question
  "must name the exact return columns". Scoring ignores column names. **My error.**
- **Path-counting questions** ("how many complete routes run from … do not reuse a connection")
  are valid queries no person would ask.
- **Low diversity, measured:** 78.7% of filter uses anchor on a numeric id (name, title or tag
  name: 11.7%); 59.9% of instances return one column aliased `value`.
Training on this would teach a distribution unlike the evaluation set. Amendments B1–B6 are in
`datagen/SPEC.md` and queued to Codex: ordinary vocabulary, no alias instructions, naturalness
decided per structure before the split with removals reported by component, varied anchors and
return shapes, deterministic hints at the evaluation rate, non-templated question writing. The
pilot is to be redone before anything is scaled. Usable training-set size is unknown until then.

## 2026-10-03 — independent evidence on what people ask; one of my instructions was backwards

The Fireworks agent classified 6,601 human-written question–SQL pairs from BIRD's official
filtered training split (69 databases, the evaluation database not among them; 0 unclassified;
labels cross-checked by a second method with 10 disagreements, all one construct). Ledger F40–F43.
- **Anchors:** people filter on a string in a non-id column 77.1% of the time and on a numeric
  id 6.4%. This supports the direction of amendment B4 from evidence that is not the evaluation set.
- **Return width — my B4 was wrong in direction.** People ask for a single column 83.9% of the
  time. I had told the generator to vary away from single-column returns. The fault in the first
  output was the fixed alias, not the width. Corrected in amendment C1.
- **Depth:** 79.0% of human questions need at most one relational hop (an upper bound on graph
  hops). The first generated output had 15.0% of instances at ≤1 hop and 52.0% at 3–4 hops.
**Position changed, with the evidence above:** I had said the generated distribution would not be
tuned toward this measurement. A training set that is 15% shallow against human asks that are
79% shallow is a mismatch large enough to matter for a milestone judged on human-written
questions, so amendment C2 weights *instances* toward shallow structures while keeping every
deep structure for the held-out analysis. The source is an independent human set, not the 186.

## 2026-10-03 — C2 revised: it is a target, its numbers were stale, and it had a hidden cost

Three corrections from the Fireworks agent, each verified from the files on disk:
- **Stale figures in binding text.** I quoted the first output as 15.0% shallow and 52.0% deep;
  those came from an interim report read earlier. From the files: 853 of 5,590 = 0.153 at ≤1 hop,
  2,925 of 5,590 = 0.523 at 3–4 hops. Spec corrected.
- **It is a target, not a check**, and is now declared as one in `PLAN.md`: the depth mix follows
  BIRD's training split, so the post may not say the data was designed without reference to the
  benchmark.
- **Hidden cost.** The training split has 58 structures at ≤1 hop; at 12 instances each that is
  696 shallow instances, so a floor of half caps the training set at 1,392; the 15% deep cap is
  then 209 instances over 197 deep training structures, 1.06 each — "retained" in name only.
  Resolution: every training structure gets 6–12 instances; only as many deep structures as that
  allows stay in training (at most 34 at six each on the first output's counts); the rest move to
  the held-out split. The earlier ≥1,500-instance target is dropped. Budget, not data volume, is
  the binding limit on training length.

## 2026-10-03 — small corrections and a division of labour

- **Rounding.** The entry above says 209 deep instances; "at most 15%" of 1,392 is 208 (208.8
  floored). Nothing downstream changes: 34 deep structures at six instances each.
- **Fireworks prices now have two official sources** (Fireworks agent, ledger F45): $13.00 per
  B200-hour on the public pricing page as well as in the cost catalog. Start-up time is stated
  there as not charged; whether a trainer's initialisation is billed is unsettled.
- **Owner's direction:** facts and verification about the Fireworks platform belong to the
  Fireworks agent, not to me. I checked one of her claims independently when asked whose claim it
  was; routine lookups on that platform go to her from here on.
- **Owner's idea, assessed:** train a different student on Fireworks, suggested Gemma 4.
  Fireworks' fine-tuning models page (my read through a fetch summary; hers to confirm) lists
  Gemma 4 only as 26B and 31B, dedicated 4 × B200, no per-token training — $52/hour, 2.84 hours
  of the $147.88 balance — so it worsens the billing problem and is not a small model. The page
  lists six models with per-token training; she is checking which, if any, is cheap, supports RL
  per token, has headroom and can be rendered by the existing harness. Not before milestone 1.

## 2026-10-03 — owner's go-ahead for Tinker runs; E4 preflight (written before anything bills)

**Decisions by the owner today:** student is Qwen/Qwen3.5-9B, trained on Tinker; the Fireworks
arm is decided after this result. Opening Tinker balance **$128** (owner's statement, 2026-10-03).
Everything a run writes is mirrored to object storage (`monitor.py`): metrics, rollout summaries,
transcripts, config and figures. All earlier baseline runs were mirrored today as well.

**Plan.** E4a: a two-update smoke run to measure what is currently unknown — real cost per step,
datums per trajectory, training tokens per rollout, the fraction of groups removed as
constant-reward, per-group reward spread, and whether the reasoning renderer breaks prefix
extension. E4b: the first real run, **RL from the base model with no supervised warm start**,
sized from E4a's measured cost. Reasons for no warm start first: the 9B already calls the tool
on every question (no_query 0 in E3) and scores 0.425, so RL has signal; the stored queries are
in a machine style unlike anything a model writes; and a warm start on a reasoning model needs
demonstrations with reasoning, which the generated data does not have.

**Rule-7 preflight (E4a and E4b).**
1. *Timestamped progress per unit of work?* `rl.train` logs each iteration to `metrics.jsonl` and
   the console; the monitor prints a line every sync.
2. *Results on disk incrementally?* `metrics.jsonl` and rollout summaries are appended per
   iteration; checkpoints every `save_every`; the monitor mirrors to object storage on a timer.
3. *Does working memory grow?* Rollouts are per-iteration; database rows are capped at 25,000 per
   re-execution and 50 shown to the model; the driver pool is capped at 24 connections.
4. *If killed at 80%?* The last saved checkpoint and every logged iteration survive locally and
   in object storage; `behavior_if_log_dir_exists=resume` continues from the checkpoint.
**Cost bound.** No rented GPU and no idle billing: Tinker bills per token. The bound is
`max_steps` × groups × rollouts. E4a: 2 steps × 8 groups × 8 rollouts = 128 rollouts. Upper-bound
estimate from E3 token counts and list prices: 128 × $0.01454 = $1.86. E4b's `max_steps` is set
from E4a's measured cost, not from the dataset size, with a stated dollar ceiling.
**Not billed by time, so no idle watchdog; the watchdog is the step cap plus the monitor.**
**Blocked on:** natural-language questions for the generated instances (Codex, in progress).

### E4a RESULT — RL smoke run, Qwen3.5-9B, 2 updates × 8 groups × 8 rollouts (2026-10-03 11:07–11:10)

Data: 34 pilot training questions (16 used), written by Codex under the amended spec, hints on
33 of 34. Checkpoint `tinker://d1bd0f5c-…:train:0/sampler_weights/final`.
Before launch I found `train.py` did not load the project env file, so the run would have been
billed to whichever API key the shell exports — a different key from the project's. Fixed first.

| measured | step 0 | step 1 |
|---|---|---|
| reward (mean partial credit, kept groups) | 0.363 | 0.355 |
| strict-correct | 0.357 | 0.359 |
| constant-reward groups dropped | 1 of 8 | 3 of 8 |
| turns per rollout | 5.89 | 4.97 |
| prompt tokens per rollout (summed over turns) | 10,261 | 8,214 |
| sampled tokens per rollout | 1,768 | 1,560 |
| wall time | 80.6 s | 91.5 s |
| sampler-vs-trainer KL | 0.00024 | 0.00027 |

**What it settles.**
- *Is there a learning signal?* Yes. Of 16 groups, 9 have a reward spread of at least 0.82
  (some rollouts fully right, some fully wrong) and 4 are constant and dropped (0.25). The worry
  that the reward is binary on most failures does not bite here, because the same question is
  often solved by some rollouts and missed by others.
- *Datums per trajectory?* 102 datums for 96 trained trajectories = 1.062. Multi-turn trajectories
  merge into one training sequence, so training tokens are near the low bound (about 2,300–2,900
  per rollout), not one sequence per turn.
- *Does the reasoning renderer break prefix extension?* No, by the same evidence, and the small
  sampler-vs-trainer KL says the trainer sees what the sampler produced.
- *Cost.* From logged tokens at list prices, prompt priced uncached: $0.79 per 64-rollout step,
  $1.58 per 128-rollout step, $1.58 for this smoke run. An estimate until billing data arrives.
- *Generated questions are longer work than the evaluation ones:* 9,238 prompt and 1,664 sampled
  tokens per rollout against 5,322 and 937 on the 186, with 5.43 turns against 3.88.
- 4-hop questions: 0 of 8 strictly correct in step 0 (partial credit 0.012) — the hardest slice.
**Not settled:** whether reward rises over more updates (two steps cannot show it); the exact
bill; and LoRA alpha (the checkpoint exists now, so it can be read from the exported adapter).

**Sizing E4b from these numbers.** 30 steps of 16 groups × 8 rollouts is an estimated $47.26 and
needs 480 distinct training questions; 40 steps is $63.02 and 640. Codex is writing them now.
Meanwhile three more zero-shot passes of the 9B on the 186 are running, to give the four-sample
baseline that the pre-registered bar is defined on.

**Pre-registration addendum, written before E4b starts (2026-10-03).** Milestone 1 is RL from
the base Qwen3.5-9B with the partial-credit reward. A supervised warm start, if it is run, is a
separate arm and a separately labelled claim; it does not count toward milestone 1. The bar
(≥5 points on the 186 with a bootstrap interval excluding zero, simple tier not down by more than
3) is evaluated on a four-sample baseline and a four-sample evaluation of one checkpoint, chosen
on generated `heldout_instance` data only.

### E4a correction — my datums-per-trajectory figure was wrong (found by the Fireworks agent, verified here)

I reported 1.062 datums per trajectory and concluded that multi-turn trajectories merge into one
training sequence and that training was "near the low bound". I had noted while computing it that
the log might print only a sample, and then wrote the conclusion down as settled anyway. It was
a sample: the 102 markers belong to the 16 trajectories the logger prints.
**Verified three ways.** (1) The log context shows per-trajectory printing under a
"Trajectory Group" header. (2) A turn can extend the previous training sequence only if its
prompt is at least the previous prompt plus the previous action; on kept trajectories that
fails on 162 of 257 transitions in step 0 and 116 of 182 in step 1. The renderer drops earlier
reasoning from the history, so the next prompt is shorter than what was sampled. (3) The
cookbook's `trajectory_to_data` returns a single datum only when every observation contains the
previous observation plus action as a prefix.
**Corrected figures, from datum boundaries:** 3.89 and 3.90 datums per kept trajectory; 7,936
and 7,934 training tokens per kept rollout; $1.309 and $1.010 per 64-rollout step, mean $1.16;
the smoke run cost an estimated $2.32, not $1.58. Training is about half the cost, not a quarter.
**What does not change:** the learning signal (9 of 16 groups with spread ≥ 0.82, 0.25 dropped
as constant), wall time, and the KL check — which shows the trainer reproduces what the sampler
saw, true with one datum per turn as much as with one per trajectory.
**Run 1 resized before launch.** 30 steps of 16 × 8 would be an estimated $69.59, not $47.26.
Instead: 8 groups × 8 rollouts, staged — 20 steps (estimated $23.20, 160 questions), extended to
40 (estimated $46.40, 320 questions) only if the reward curve is rising and the bill agrees with
the estimate. Learning rate 1e-5 is inside the cookbook's own guidance for RL (1e-5 to 4e-5;
its multi-turn RL example uses 1e-5), checked today in `skills/research`.

### E4a correction, second time — the segment model is also wrong; training is one datum per turn

After withdrawing 1.06 datums per trajectory I replaced it with about 3.9, counting a new datum
only where the next prompt was *shorter* than the previous prompt plus action. The Fireworks
agent pointed out that this is a necessary condition for merging, not a sufficient one: the
renderer removes earlier reasoning (shortening the prompt) and appends a tool result
(lengthening it), so a prompt can be longer and still not contain the previous sequence.
**Verified.** `rl/train.py` prints one marker per datum returned by `assemble_training_data`,
the trainer's own function. The printed group that matches unambiguously — iteration 0, group 0,
rewards 0.237/0/0/0 with 7/8/8/8 turns — prints 7/8/8/8 datums; my segment model says 3/5/6/4.
So the datum count is the turn count. **I have now been wrong twice on this one number**, both
times by inferring from a proxy instead of reading the code that produces it.
**Figures to use:** $1.404 per 64-rollout step at list prices (sampling $0.659 and $0.546,
training $0.947 and $0.656 in the two steps); the smoke run cost an estimated $2.81; 20 steps of
8 × 8 is $28.08 and 40 steps is $56.16. The $23.20 and $46.40 figures above are withdrawn.
Billed training tokens for the smoke are expected near 1,095,448; the bill has the last word.

### E5 RESULT — four-sample zero-shot baseline, Qwen3.5-9B on the 186 (2026-10-03)

Per-pass strict 0.425, 0.419, 0.419, 0.419 (lenient 0.591, 0.554, 0.565, 0.586).
**Per-question mean over four samples: 0.4207, 95% bootstrap interval 0.363 to 0.481.**
Simple 0.477 (151), moderate 0.183 (30), challenging 0.150 (5).
Solved in 0/1/2/3/4 of four samples: 72 / 28 / 21 / 17 / 48 — so 66 questions are mixed, 72 never
solved, 48 always solved. Upper-bound cost of the four passes $4.16.
This is the "before" number the pre-registered bar is defined against. A gain needs a point
estimate of at least 0.4707 after training with an interval on the paired difference above zero;
the reference is 0.608 (single sample of the 27B on each platform).

## 2026-10-03 — E4b stage 1 launched: RL from base, Qwen3.5-9B, 20 steps × 8 groups × 8 rollouts

**Data.** Snapshot of Codex's amended, rebalanced output (431 structures, 4,982 instances; training
split 1,331 instances with 0.50 at ≤1 hop and 0.15 at 3–4 hops) and her first 200 individually
written training questions, covering 135 distinct structures. Training file `train_200.jsonl`
built by `datagen/build_training_file.py`; snapshot mirrored to object storage. Stage 1 uses 160
of the 200 (one epoch, seed 0). No evaluation split exists yet, so there is no in-loop evaluation;
checkpoints are saved every 5 steps for selection afterwards on generated held-out data.
**Config.** `train.py` defaults: LoRA rank 32 without an unembedding adapter, learning rate 1e-5,
`importance_sampling`, no KL penalty, constant-reward groups removed, T = 1.0, ≤8 turns.
**Cost bound.** 20 steps × $1.404 = $28.08 estimated at list prices; bounded by `max_steps`.
Balance before launch, estimated: $128.00 opening − $2.81 smoke − $3.16 for three baseline
passes = $122.03. Stage 2 (to 40 steps) only if the reward curve is rising and the bill for the
smoke run agrees with the per-turn estimate.
**Operational.** Launched detached so the session's 30-minute limit on background commands
cannot kill it; the machine is kept awake for the duration; the monitor mirrors logs and curves
to object storage every two minutes. If it dies, `behavior_if_log_dir_exists=resume` continues
from the last checkpoint.
**To report afterwards (requested by the Fireworks agent):** which of the three baseline groups
moved on the 186 — the 72 never solved, the 66 mixed, the 48 always solved.

### E4b stage 1 RESULT — RL from base, Qwen3.5-9B, 20 steps (2026-10-03 11:23–11:57)

1,280 rollouts on 160 generated questions (one pass, no question repeated). Checkpoints at steps
5, 10, 15, 20: `tinker://46c8a099-6440-5f1e-8bf0-c865463ddbc2:train:0/sampler_weights/0000NN`.
- **In-run reward shows no trend** (mean over all 64 rollouts: first five steps 0.528, last five
  0.483) — but every step uses different questions, so this is not a measurement of learning.
- 31.9% of groups were dropped as constant-reward (smoke: 25%).
- Tokens: 9,172,357 prompt, 1,920,043 sampled, 7,576,241 trained. **Estimated cost $20.97** at
  list prices (sampling $9.88, training $11.08), under the $28.08 bound: rollouts on this
  training set are shorter than in the smoke run and more groups were dropped.
- Wall time 34.2 minutes. Six of twenty steps exceeded 150 s because one rollout's query ran to
  the 120 s database timeout while the other 63 rollouts waited (e.g. joining comments to users
  by display name, which no index supports). On per-token billing this costs time only.
- Sampler-vs-trainer KL stayed between 0.00011 and 0.00057.

### E6 RESULT — checkpoint selection on generated held-out instances (264 questions, 1 sample each)

| checkpoint | strict | lenient | turns | hops 0 / 1 / 2 / 3 / 4 |
|---|---|---|---|---|
| base | 0.504 | 0.606 | 4.60 | 0.939 / 0.480 / 0.505 / 0.286 / 0.125 |
| step 10 | 0.534 | 0.610 | 4.36 | 0.970 / 0.580 / 0.441 / 0.214 / 0.292 |
| step 20 | **0.602** | 0.667 | 4.19 | 0.879 / 0.660 / 0.548 / 0.357 / 0.333 |

Paired over the same 264 questions: step 20 − base **+0.098**, 95% bootstrap [+0.034, +0.163]
(better on 51, worse on 25); step 10 − base +0.030 [−0.038, +0.098]; step 20 − step 10 +0.068
[+0.004, +0.136]. These are unseen parameter values of *trained* structures, generated data, one
sample per question — evidence that training is working, not yet the milestone. Upper-bound cost
of the three passes $5.76.

**Decision: extend training (stage 2), and do not look at the 186 yet.** The pre-registration
says the selected checkpoint is evaluated on the 186 once. Evaluating step 20 there now and a
later checkpoint afterwards would be two looks, so the 186 waits until training has stopped.
**A stated deviation.** I had said stage 2 would start only if the curve was rising *and* the
smoke run's bill agreed with the estimate. The curve is rising. The bill is not available:
the billing API returned no token rows for today at 06:36 UTC. I am extending without that
check, because the estimate prices prompts uncached and training at one datum per turn, so the
bill should not exceed it, and `max_steps` bounds the spend either way. Estimated balance before
stage 2: $95.30 ($128 opening less $32.70 estimated). Stage 2 is 17 more steps to step 37 — the
end of the same 300-question file, so no question repeats — estimated $17.82.

## 2026-10-03 — review of stage 1 by the Fireworks agent: corroboration, the timeout, unpriced costs

- **Reproduced** from the three run folders: 0.504 / 0.534 / 0.602 and both paired intervals.
- **Corroboration independent of the scorer** (her measurement, ledger): from base to step 10 to
  step 20, rollouts cut off by the turn cap fall 82 → 74 → 59, mean turns 4.60 → 4.36 → 4.19,
  query errors 229 → 215 → 206, while sampled tokens per question stay flat (1,374 to 1,400). The
  policy reaches an answer in fewer turns with fewer failed queries; it is not thinking longer.
- **Limits she states and I accept:** one sample per question; the held-out instances share
  structures with training; "still rising" (step 20 − step 10) rests on a lower bound of +0.004.
- **The database timeout is bimodal** (her analysis of `timing_spans.jsonl`): of 6,424 calls in
  stage 1, 6,375 finish under 1 s, the slowest success is 23.8 s, nothing falls between 30 and
  119 s, and 9 run to the 120 s timeout. The six slow steps account for 37.2% of wall time.
  **Decision for the next run, not this one:** a 45 s per-query limit in training, set as the
  transaction timeout so the model sees the same error text, pinned in `rl_env.py` and declared;
  the evaluation harness stays at 120 s because every baseline was measured there. 45 s is above
  every successful call in both the generated and the benchmark replay.
- **Unpriced items in my extension reasoning.** The held-out evaluations ($5.76) were in my
  balance estimate. Checkpoint storage was not: measured today, 26 checkpoints totalling
  30.84 GB, of which 14 created today total 9.69 GB — $0.97 per month for today's at $0.10 per
  GB-month (price read from the docs on 2026-09-21, not re-read today). Not a budget risk.
- **No bill has yet confirmed any token accounting.** The console balance against the $128
  opening figure is the single number that validates or breaks every estimate; to be asked of
  the owner on his return.

**Pre-registration addendum 2, written before any held-out-structure evaluation (2026-10-03).**
The held-out-structure questions are much deeper than the training and held-out-instance ones
(share at 3–4 hops: 0.600 against 0.158 and 0.144, recomputed from the question file), a direct
consequence of moving deep structures out of training. A raw drop from held-out instances to
held-out structures would therefore be mostly a depth effect and would overstate the cost of
novelty. So: (1) held-out-structure results are reported **by hop**, beside held-out-instance
results at the same hop; (2) **the novelty claim rests on the two-hop comparison only** — 109
unseen-structure questions against 93 seen-structure ones; (3) results at 3 and 4 hops are
descriptive, because the seen-structure side there has 14 and 24 questions; (4) novel-combination
and novel-component are reported separately within that. Found by the Fireworks agent's join of
the data files; the confound comes from a choice both of us made.
**Known mismatches with human-written questions, recorded as limitations, not changed mid-run**
(her measurement): sum, avg, min and max together are 48.7% of training questions against 12.2%
of human asks in BIRD's training split, and plain lookups are under-represented (31.7% against
54.6%); 15.3% of training questions ask for an ordering with no limit, which the order-insensitive
scorer cannot reward or test, so nothing may be claimed about learning to order results.

**Pre-registration addendum 3, written while no trained checkpoint has been evaluated on the 186
(2026-10-03, proposed by the Fireworks agent, agreed here).**
1. Whatever run 1's selected checkpoint scores on the 186 **is** the milestone 1 result, reported
   as it is, hit or miss.
2. Any later run evaluated on the 186 is a separate, labelled result. The write-up reports all of
   them, including the first if it missed. Nothing is replaced.
3. If a second data pass happens, what it changes must be fixed from evidence that is **not** the
   186. The aggregation mix measured against BIRD's training split qualifies: it was measured
   before any result and comes from other databases. A change motivated by which of the 186
   questions failed does not qualify — that would turn the held-out set into a development set.
4. Failures on the 186 may be described in the write-up (which group moved, by tier), but not
   mined to decide what training data to add. If a development set of human questions is wanted
   for that, BIRD's dev split has ten other databases never used here; that needs its own graph
   and is an option, not a plan.
I had written earlier today that if run 1 fell short, the aggregation mismatch would be my first
suspect and worth a second pass. That intention stands only under point 3.

### E4b stage 2 RESULT and checkpoint selection (2026-10-03 12:07–12:38)

Stage 2 ran steps 20–36 (17 steps, 1,088 rollouts) for an estimated $14.12; 41.2% of groups were
dropped as constant-reward, up from 31.9% in stage 1. Run 1 in total: 37 steps, 2,368 rollouts,
296 distinct questions, estimated $35.09.

| checkpoint | held-out-instance strict (264, 1 sample) | Δ vs base, 95% paired bootstrap | turns | turn-cap hits | query errors |
|---|---|---|---|---|---|
| base | 0.504 | — | 4.60 | 82 | 229 |
| step 10 | 0.534 | +0.030 [−0.038, +0.098] | 4.36 | 74 | 215 |
| step 20 | 0.602 | +0.098 [+0.034, +0.163] | 4.19 | 59 | 206 |
| step 30 | 0.636 | +0.133 [+0.064, +0.197] | 3.85 | 45 | 183 |
| **step 37** | **0.678** | **+0.174 [+0.110, +0.242]** | 3.67 | 45 | 176 |

**Selected checkpoint: step 37**, the best on generated held-out instances, chosen without any
look at the 186. `tinker://0cdf64fc-e5c9-5c9d-8d79-1626d6e4db44:train:0/sampler_weights/final`.
Accuracy was still rising when the planned 37 steps ended; training stops here as planned, and
any continuation is a separate, labelled run under pre-registration addendum 3.
**Next, once:** this checkpoint on the 186 at four samples (the milestone-1 result, hit or
miss), and base and this checkpoint on the 360 held-out-structure questions, read by hop.
Estimated balance before these evaluations: $77.92.

### E7 RESULT — MILESTONE 1: the selected checkpoint on the 186, four samples (2026-10-03)

Reported as pre-registered: once, hit or miss.

| | strict, per-question mean over 4 samples |
|---|---|
| Qwen3.5-9B before training | 0.4207 |
| after 37 steps of RL from base (step-37 checkpoint) | **0.4664** |
| paired difference | **+0.0457**, 95% bootstrap [+0.0094, +0.0820] |
| reference (Qwen3.8-27B, single sample) | 0.608 |

**The pre-registered bar is NOT met.** It required the interval's lower bound to be above zero
*and* a point estimate of at least +0.05. The interval excludes zero; the point estimate is
+0.0457, short by 0.0043. By the rule both agents signed before training, this is reported as
not clearing the bar. It is a real, statistically positive improvement of about four and a half
points, and it closes 24.4% of the gap to the reference. It is not the result the bar asked for.
The forgetting guard is met: the simple tier rose (0.477 → 0.525).

**Where the change came from.**
- By tier: simple +0.048, moderate +0.050, challenging −0.050 (5 questions).
- By baseline group: the 72 questions never solved in four baseline samples rose to 0.125 and
  contribute +0.0484; the 66 mixed questions rose 0.458 → 0.511 (+0.0188); the 48 always-solved
  questions fell to 0.917 (−0.0215). So training unlocked some previously unsolved questions and
  cost some reliability on previously certain ones.
- **Lenient accuracy barely moved: 0.5739 → 0.5766.** Lenient counts an answer whose values are
  right even if its shape is not. Strict rose by 0.0457 and lenient by 0.0027, so on the
  benchmark most of the gain is answers that were already right in substance becoming right in
  form. That is a narrower achievement than "the model got better at graph questions".
- The gain on generated held-out questions was much larger (+0.174 on 264) than on the benchmark
  (+0.046 on 186): the policy learned the generated distribution better than it transferred.

Under pre-registration addendum 3 this stands as the milestone-1 result. Any further run is a
separate, labelled result, and any change to the data must be justified by evidence that is not
the 186. Upper-bound cost of the four passes: $3.95.

### E8 RESULT — unseen query structures, read by hop as pre-registered (2026-10-03)

360 generated questions on structures never trained, one sample each.

| | n | base | trained (step 37) | change, 95% paired bootstrap |
|---|---|---|---|---|
| all unseen structures | 360 | 0.294 | 0.447 | +0.153 [+0.094, +0.211] |
| novel combination | 151 | 0.285 | 0.470 | +0.185 [+0.099, +0.272] |
| novel component | 209 | 0.301 | 0.431 | +0.129 [+0.053, +0.206] |

By hop, unseen structures beside seen structures (held-out instances):

| hops | unseen: n, base → trained, change | seen: n, base → trained, change |
|---|---|---|
| 0 | 16, 0.625 → 0.688, +0.062 [−0.125, +0.250] | 33, 0.939 → 0.970, +0.030 |
| 1 | 19, 0.421 → 0.789, +0.368 [+0.105, +0.632] | 100, 0.480 → 0.700, +0.220 [+0.100, +0.340] |
| **2** | **109, 0.422 → 0.514, +0.092 [−0.009, +0.193]** | **93, 0.505 → 0.656, +0.151 [+0.043, +0.258]** |
| 3 | 92, 0.250 → 0.457, +0.207 [+0.098, +0.315] | 14, 0.286 → 0.357 (descriptive) |
| 4 | 124, 0.153 → 0.298, +0.145 [+0.048, +0.242] | 24, 0.125 → 0.458 (descriptive) |

**The pre-registered novelty claim (two hops).** On seen structures the gain is clear
(+0.151, interval above zero). On unseen structures at the same depth it is +0.092 with an
interval that reaches just below zero, and within that, novel combinations gain +0.156
[−0.022, +0.333] and novel components +0.047 [−0.078, +0.172]. The ordering matches the earlier
graph project (recombining trained parts transfers better than a part never seen), but **at two
hops neither interval excludes zero, so this run does not establish it**. What the aggregate does
show is that training on 135 structures did not merely memorise them: accuracy on 296-structure
unseen data rose by 0.153 overall, and the rise appears at every depth.
Upper-bound cost of the two passes: $6.88. Estimated balance after all of today's work: $67.09
of the $128 opening figure (training $35.09, evaluation $23.01, smoke $2.81), still unconfirmed
by any bill.

### E7 correction — my group breakdown was a regression-to-the-mean artefact

I reported that the 72 never-solved questions rose to 0.125, the 48 always-solved fell to 0.917,
and concluded that training "unlocked some previously unsolved questions and cost some
reliability on previously certain ones". The groups were defined on the same four baseline
passes that served as the baseline. A question that scored 4 of 4 was partly lucky and scores
lower on any re-evaluation; one that scored 0 of 4 was partly unlucky and scores higher.
**The artefact, measured with no training:** groups defined on two baseline passes and read on
the other two give +0.117 for "never" and −0.128 for "always" — as large as what I reported.
**Unbiased** (groups on two baseline passes, baseline on the other two, six splits averaged):

| group | before | after | per-question change | contribution to the mean |
|---|---|---|---|---|
| never solved | 0.117 | 0.178 | +0.061 | +0.0293 |
| mixed | 0.425 | 0.511 | +0.086 | +0.0166 |
| always solved | 0.872 | 0.871 | −0.001 | −0.0002 |

So: **no evidence of lost reliability**; the per-question gain is largest in the mixed group,
which is what group-relative RL should produce; the never group contributes most in total only
because it is the largest. Found by the Fireworks agent, who had asked for the breakdown.
**Form share, quantified (her measurement, verified):** right-values-wrong-shape fell 0.1532 →
0.1102; 94.1% of the strict gain on the 186 is form. The reward gives nothing for right values in
the wrong shape, so shape is what it teaches. On human questions the policy learned to return
what was asked for; it did not learn to answer more questions.
**On the miss:** the gain is 2.8 sampling standard errors (real); the shortfall of 0.0043 is
0.27 of one. A threshold on a point estimate clears only about half the time when the true
effect sits on it. That is a property of the bar we signed, stated as a fact about it and for no
other purpose: the bar was read once and is not re-read.

### E7 reading, corrected — the reward is not what limits substance

I proposed that the two suspects divide the blame: the question mix explains why generated-data
skill does not carry to human questions, and the reward's blindness to shape explains why what
carries is form. The Fireworks agent tested the second half with data already on disk, and it
fails. If the reward could only teach form, the gain would be mostly form everywhere.

| question set | strict gain | lenient (substance) gain, 95% interval | substance share |
|---|---|---|---|
| generated, seen structures (264) | +0.174 | +0.102 [+0.042, +0.163] | ~59% |
| generated, unseen structures (360) | +0.153 | +0.117 [+0.058, +0.178] | ~76% |
| human, the 186 (four samples) | +0.046 | +0.003 [−0.031, +0.036] | ~6% |

The same reward taught the policy to get 10 to 12 more points of answers right *in values* on
generated questions, including on structures it never trained on. On human questions that gain
is absent. So form — "return what was asked and nothing else" — is a habit that crossed between
question styles, and substance was learned for the kinds of question the generator writes and
did not cross. That is the distribution explanation doing all the work. **My statement that a
second run fixing only the question mix would leave a reward problem in place is withdrawn:** on
this evidence a change to the reward is aimed at the wrong thing, and a change to the question
mix at the right one. The shares on generated sets are single-sample point estimates and are to
be quoted as approximate; the direction is not in doubt, since both lenient intervals exclude zero.

## 2026-10-03 — balance reconciled against the console

The owner read the console after all runs: **$83.04**. Opening figure before the runs: $128
(his statement; he is not certain of the exact value, and $129.03 was the console reading on
2026-09-22). **Actual spend: $44.96** (or $45.99). My running estimate was $60.91.
Recomputed from every run folder since the opening: 38,096,750 prompt tokens, 7,927,081 sampled,
13,635,401 trained under the one-datum-per-turn model. At list prices: $60.91 if no prompt token
was cached, $40.79 if all were. The bill sits between the two and implies roughly 0.79 of prompt
tokens were cache hits — the same range inferred from the 27B baseline in September.
**What this confirms and what it does not.** It confirms that the estimates were upper bounds
and conservative by about a quarter, so extending to stage 2 without the bill did not overspend.
It is consistent with the per-turn training model. It does not by itself distinguish that model
from the withdrawn alternatives, because the cache share is a free parameter; the billed
training-token count from the usage API would, and that API has still returned no token rows.
**Checkpoint retention (from the console):** periodic checkpoints expire in 7 days; `final` ones
never. The selected checkpoint is a `final` and is kept; steps 10 and 30 will expire around
2026-10-10, before the write-up deadline. Their held-out evaluations are already stored.

## 2026-10-03 — checkpoints preserved outside Tinker; two open questions closed

The adapters for steps 10, 20, 30 and the selected step 37 are now in object storage (1.384 GB),
downloaded with `tinker checkpoint download` and removed from the laptop afterwards. Periodic
checkpoints expire on Tinker after 7 days, and credits expire on 2026-11-13, so the copies are
the durable record. Only sampler weights can be downloaded; the training state (needed to resume
with optimiser state) cannot.
Closed by reading the exported adapter: **LoRA alpha is 32 at rank 32** (the value the Fireworks
SDK pins, so the two platforms match on scale), and the adapter contains **no unembedding
tensors**, confirming the `train_unembed=False` setting applied.
**Source of "what people ask"** (asked by the owner): BIRD's official filtered training split,
`birdsql/bird23-train-filtered` on Hugging Face — 6,601 human-written question–SQL pairs over 69
databases, none of them the evaluation database, CC BY-SA 4.0. I verified the source, size and
licence from the Hugging Face API; the shape classification was done by the Fireworks agent and
I have not re-run it myself. Its limits: the questions were written by the benchmark's annotators
for SQL on other databases, so "what people ask" means "what that benchmark's annotators wrote".

## 2026-10-03 — E9 pre-registration: run 2, a human-like question mix (written before any data or run exists)

**Hypothesis.** The first run's gain did not carry to human questions because the training
questions do not resemble them in shape. Evidence, all predating the milestone result and none
from the 186: sum / avg / min / max are 48.7% of training questions and 12.2% of human asks;
plain lookups 31.7% against 54.6%.
**Prediction.** Training on a set whose shape mix follows the human one raises accuracy *in
substance* on the 186, i.e. lenient accuracy, which run 1 left flat (+0.003).
**Design — one thing changes.** Same model (Qwen3.5-9B from base), same 37 steps × 8 groups × 8
rollouts, same learning rate 1e-5, rank 32, no unembedding adapter, same reward, same prompt and
tool. The training file is the new 320-question set of amendment D. One declared environment
difference: a 45 s per-query limit in training (`TrainingCypherTool`), which over run 1's 6,424
calls would have changed no outcome; evaluation keeps 120 s.
**Evaluated checkpoint fixed in advance: step 37.** No selection, so no held-out set is needed to
choose, and the number of updates equals run 1's selected checkpoint.
**Evaluations.** The 186 at four samples; the same 264 held-out-instance and 360
held-out-structure questions as run 1, one sample each.
**How it will be read.**
1. *Run 2 against the baseline (0.4207):* the same bar as milestone 1 — lower bound above zero
   and at least +0.05. Reported as "run 2", a separate result; milestone 1 stands as it is.
2. *The hypothesis test:* lenient accuracy on the 186, run 2 minus baseline, paired bootstrap.
   Interval above zero → substance transferred, hypothesis supported. Interval including zero →
   not supported by this run.
3. *Run 2 against run 1 on the 186:* paired, descriptive.
4. The held-out generated sets follow the *old* mix, so run 2 may do worse there than run 1; that
   would not count against the hypothesis and is reported as it comes.
**Cost bound.** Training at most 37 steps; run 1's training was estimated at $35.09 and billed
about a quarter less. Evaluations estimated at $9. Console balance before: $83.04.

**E9 pre-registration, revised after review by the Fireworks agent — still before any run-2 data
has been used or any run started (2026-10-03).** Four changes; the earlier E9 text is superseded
where it differs.
1. **The confirmatory test is run 2 against run 1, not against the baseline.** The hypothesis is
   that the question mix matters; a run with any mix might move lenient accuracy a little. So the
   test is the paired difference in *lenient* accuracy on the 186 between run 2 and run 1, each
   at four samples: interval above zero → supported; otherwise not supported by this run. Run 2
   against the baseline remains the test of the bar and is reported as a separate result.
2. **Stated limitation: one run per arm cannot separate the mix from run-to-run variance.** Two
   runs on the same data with different seeds would not score identically on the 186, and that
   spread has never been measured here. A win for run 2 is what the hypothesis predicts and also
   what seed noise could produce. If budget remains, a repeat of run 1's data with a different
   seed is the measurement that would settle it.
3. **Three things differ between the runs, not one:** the training file; the 45 s per-query limit
   in training, which also bounds the reward's uncapped re-execution of the final query (evidence
   that it is immaterial: no call in run 1 finished between 30 s and the limit, and no rescore
   failed in any of 37 steps); and how the evaluated checkpoint is chosen (run 1: best on
   held-out instances, which was the last step; run 2: the last step, fixed in advance).
4. **Step 30 is evaluated on the generated sets only**, as a descriptive check in case step 37
   lands on an anomalous update. It is never evaluated on the 186.
Also recorded: the "how many" target is one combined figure of about 28%, and the 10% of
training questions at 3–4 hops is a declared departure from the human 4.2%.

**E9 addendum: what follows run 2 is decided now, not after the result (2026-10-03, proposed by
the Fireworks agent, adopted before run 2 exists).** The remaining Tinker budget covers run 2 and
one further run of about the same size, not two (ledger W8; those figures are the Fireworks
agent's estimates from the run folders and have not been recomputed here). Choosing that further
run after seeing run 2 would be a forking path, so the rule is fixed in advance, keyed on the
confirmatory test (paired lenient difference on the 186, run 2 minus run 1):
- **Interval touches zero** → a seed repeat of run 1's data. Only that can make the comparison
  readable; a longer run would say nothing about the hypothesis.
- **Interval clearly above zero** → 37 more steps of the run 2 arm, as a labelled extension. This
  needs more new-mix questions than the 320 specified, or a second pass over the same ones; which
  of the two is stated when it is run.
- **Run 2 not better** → 37 more steps of the run 1 arm on its unused training questions.
Any of the three is a separate billed run with its own preflight. A replication of run 1 on the
other platform would also measure run-to-run variance (confounded with platform if the two
disagree); it is not part of this rule because it is not yet runnable.

### E9 preflight — run 2 (written before launch, 2026-10-03)

**Opening balance: $83.03**, read from the Tinker console billing page at 15:08 (auto-reload is
off, so the balance is a hard ceiling on spend).
**What runs.** One detached pipeline: training (37 steps × 8 groups × 8 rollouts, `train.py`
defaults, seed 0, checkpoints every 5 steps), then the pre-registered evaluations — step 37 on
the 186 at four samples and on the 264 and 360 generated sets, step 30 on the two generated sets
only. Same code path as run 1 except `TrainingCypherTool` (45 s limit), tested against the live
graph today: a pathological query was stopped at 45.1 s and the database answered normally
afterwards.
**Rule-7 answers.**
1. *Timestamped progress per unit of work?* One line per iteration in `metrics.jsonl` and the
   console log; one line per question in each evaluation log; one line per stage in the pipeline
   log; one monitor line every two minutes.
2. *Results on disk incrementally?* Metrics and rollout summaries per iteration, checkpoints at
   steps 5, 10, …, 35 and 37; evaluation results appended per question. The monitor plots the
   curves (loss, reward, KL and the rest) and mirrors the run folder to object storage every two
   minutes; evaluation folders are mirrored when they finish.
3. *Does working memory grow?* No: rollouts are per iteration, at most 24 database connections,
   rows capped per query.
4. *If killed at 80%?* The last checkpoint and every logged iteration survive locally and in
   object storage; the pipeline resumes training from the last checkpoint if restarted. An
   evaluation that dies leaves its completed questions on disk and resumes.
**Cost bound.** Billed per token, no idle billing. Training is bounded by `max_steps=37` (run 1:
$35.09 estimated at list prices); evaluations by their question counts and a $6 cap each (run 1's
equivalents summed to $13.75 estimated). Total $48.84 at list prices, about $36.04 at the billing
ratio measured on run 1 (0.738). If training fails the evaluations do not start.
**Watchdog.** Not billed by time, so the step cap is the bound; the monitor and stage markers
show progress, and a failure marker is written if training exits non-zero.

**E9 data, frozen before launch (2026-10-03 15:55).** `train_320.jsonl`, sha256 `876d793e038d9867…`,
320 questions over 157 structures (56 reused from the first set, 101 new), hints on 291. Built
by Codex under amendment D; snapshot mirrored to object storage (`datagen_v4/`).
- *Checked independently by the training side* (`datagen/verify_v4.py`): no training structure
  equals a held-out signature or uses a held-out component; no instance or query shared with a
  held-out set; no question text shared with a held-out set; all 320 stored answers reproduced
  from the live graph; of 56 plain-count queries none differs from a distinct count; at most 5
  questions per structure. 20 instances also appear in run 1's training file.
- *Mix, from the generator's own shape tags (not re-derived from the queries):* no aggregation
  55.0%, "how many" 27.8% (count 25.0 + count distinct 2.8), sum / avg / min / max 9.7%, more than
  one aggregate 7.5%; no ordering 83.1%; ≤1 hop 70%, 2 hops 20%, 3–4 hops 10%. Negation 0%: its
  component is held out, a declared shortfall.
- *Two flaws found on reading and fixed before freezing:* 16 lookups whose answer was stated in
  the question (replaced by lookups returning a different attribute) and 14 ranges with equal
  bounds worded as ranges (reworded). The run uses 296 of the 320 (37 steps × 8, shuffle seed 0).
- A second batch of 280 with the same mix exists for the pre-registered extension (amendment D2);
  it is not used by this run and has not yet been checked by the training side.

**E9 note, recorded while run 2 trains and before any result exists (2026-10-03 16:04): the
hints are a third suspect for the transfer gap.** Found by the Fireworks agent from the files;
reproduced here with a cruder word-overlap test.
- In human-written hints the explained phrase comes from the question. A hint clause "X refers
  to Y" where X shares no word with the question occurs in 2.2% of human hints (115 of 5,121,
  BIRD training split, 69 other databases; her measurement, not reproduced here).
- In run 2's training file it is 239 of 291 hints (82.1%; my check gives the same 239). In run
  1's 300-question file my check gives 232 of 284 (81.7%); she measures 82.7% on the full 600.
  75 of run 2's hints say "score refers to Score" for a question that never mentions score: the
  generator explains fields its query carries internally, not what the question asks.
- **It is the same in both arms, so it does not confound run 2 against run 1**, and run 2 cannot
  test it. Named now so that it is not invented after the result: if run 2 does not move lenient
  accuracy on the 186, this is the next suspect. How it would act — a policy learning to discount
  hints that name fields it must not return — is a hypothesis, not a finding.
- **Decided in advance:** the extension branch of the follow-up rule uses the second batch with
  its hints as generated. Rewriting hints is a separate experiment with its own pre-registration;
  folding it into the extension would change two things at once.
- She also re-derived the mix of the 320 from the query text: it matches the generator's tags
  (lookups 55.0%, "how many" 27.8%, one returned column 84.1%, no negation). That closes the
  caveat recorded above. Two small wording defects remain in the frozen file: 7 of 26 conditional
  aggregates have a condition already decided by the range filter, and 5 questions begin
  "How many the". Gold answers are unaffected.
- The hint rate can be cited from other databases (92.8% of 6,601 BIRD training questions carry
  a hint) rather than from the 186.

### E9 RESULT — run 2, human-like question mix (2026-10-03, training 15:54–16:48, evaluations to 17:08)

**Training.** 37 steps × 8 groups × 8 rollouts = 2,368 rollouts on 296 of the 320 questions, 53.5
minutes, no errors. Checkpoints at 5, 10, …, 35 and final:
`tinker://799ed3ff-f365-5705-abf4-94e9947e88c2:train:0/sampler_weights/{0000NN,final}`.
33.8% of groups dropped as constant-reward (run 1: 36.1%). Sampler-versus-trainer KL about
0.0003 or below throughout. Tokens: 15,242,596 prompt, 3,231,424 sampled, 13,185,064 trained.
**Cost.** Estimated at list prices $35.80 training + $13.81 evaluations = $49.61. Console balance
$83.03 before, **$45.78 after** (read 17:10): **$37.25 billed**, 0.751 of the list-price
estimate (run 1's ratio: 0.738).

**All comparisons below are from one script (`e9_analyze.py`, paired bootstrap over questions,
10,000 resamples, seed 0), which reproduces milestone 1's point estimates exactly; its intervals
differ from the earlier ledger rows in the third decimal (a different random generator), so run
1 is restated here from the same script.**

| the 186 human questions, 4 samples | strict | lenient |
|---|---|---|
| baseline | 0.4207 | 0.5739 |
| run 1 (step 37) | 0.4664 | 0.5766 |
| run 2 (step 37) | 0.4758 | 0.5524 |
| run 1 − baseline | +0.0457 [+0.0094, +0.0833] | +0.0027 [−0.0296, +0.0350] |
| run 2 − baseline | **+0.0551 [+0.0202, +0.0914]** | −0.0215 [−0.0497, +0.0067] |
| run 2 − run 1 | +0.0094 [−0.0188, +0.0376] | **−0.0242 [−0.0538, +0.0040]** |

| generated held-out, 1 sample | baseline | run 1 | run 2 | run 2 − baseline | run 2 − run 1 |
|---|---|---|---|---|---|
| 264 seen structures, strict | 0.5038 | 0.6780 | 0.6667 | +0.1629 [+0.0946, +0.2311] | −0.0114 [−0.0758, +0.0568] |
| 264 seen structures, lenient | 0.6061 | 0.7083 | 0.6932 | +0.0871 [+0.0265, +0.1477] | −0.0152 [−0.0758, +0.0492] |
| 360 unseen structures, strict | 0.2944 | 0.4472 | 0.4056 | +0.1111 [+0.0528, +0.1667] | −0.0417 [−0.0972, +0.0112] |
| 360 unseen structures, lenient | 0.3611 | 0.4778 | 0.4500 | +0.0889 [+0.0278, +0.1472] | −0.0278 [−0.0861, +0.0306] |

Step 30 of run 2, generated sets only (descriptive): 0.6061 strict on the 264, 0.3944 on the
360 — below step 37 on both, so step 37 is not an anomalous update. Every pass scored all its
questions; none was skipped for budget.

**Read against the pre-registration.**
1. *The bar (strict, run 2 against baseline): met.* +0.0551 with a lower bound of +0.0202; the
   bar was a lower bound above zero and at least +0.05. 29.4% of the gap to the 27B reference
   (0.608) is closed; run 1 closed 24.4% and missed the bar by 0.0043.
2. *The confirmatory test (lenient, run 2 against run 1): not supported.* −0.0242, interval
   including zero and lying mostly below it. The prediction was that a human-like mix would raise
   accuracy in substance on human questions. It did not; lenient accuracy is, if anything, lower.
3. *Run 2 against run 1, strict: not distinguishable* (+0.0094, interval spanning zero). That run
   2 clears the bar and run 1 did not is therefore **not** evidence that the mix helped: the two
   runs differ by less than their uncertainty, and with one run per arm seed variance is
   unmeasured.
4. *Generated sets:* run 2 is a little below run 1 on both, intervals including zero. Expected
   in direction — those sets follow the old mix — and not counted against the hypothesis.

**What the two runs agree on.** On human questions the strict gain is a gain in form: the share
of questions with the right values in the wrong shape (lenient minus strict) falls from 0.1532
at baseline to 0.1102 after run 1 and 0.0766 after run 2, while lenient accuracy does not rise in
either. On generated questions both runs gain in substance as well (lenient +0.09 to +0.12).
So RL here teaches this model to return what was asked for, everywhere, and to answer more
questions correctly only on the distribution it trained on. The question-shape mix was not the
reason substance fails to transfer.

**What this does not show.** That the mix is irrelevant in general (one run per arm); that run 2
is better or worse than run 1 on anything; why lenient accuracy leans down in run 2 (not
examined yet).

**Next, by the rule fixed in advance:** the result is the "run 2 not better" branch → 37 more
steps of the run 1 arm on its unused training questions. Not launched; needs its own preflight
and the owner's go-ahead on spending most of the remaining $45.78. The hints (82% of ours explain
a term the question never uses, against 2.2% of human ones) are the named next suspect for the
missing transfer of substance, and that rule's branch does not test them.

**E9 correction to my own reading (2026-10-03, after the Fireworks agent reproduced the result
and I re-tallied her counts).** Under "What the two runs agree on" I wrote that the falling gap
between lenient and strict (0.1532 → 0.1102 → 0.0766) shows a gain in form in both runs. That
holds for run 1 and **not for run 2**. Samples by outcome, 744 per arm (186 × 4):

| | strict | lenient only | wrong | wrong at the turn cap | no query |
|---|---|---|---|---|---|
| baseline | 313 | 114 | 192 | 125 | 0 |
| run 1 | 347 | 82 | 213 | 102 | 0 |
| run 2 | 354 | 57 | 224 | 108 | 1 |

Baseline → run 1: lenient-only −32, strict +34 — consistent with answers of the wrong shape
being repaired. Run 1 → run 2: lenient-only −25 but strict only +7; the other 18 are now wrong
(+11), at the turn cap (+6) or without a query (+1), and 18 / 744 = 0.0242 is the whole lenient
drop. So in run 2 the gap shrank mostly because near-misses became misses, not because they
became correct. These are net flows between arms, not transitions of individual samples.
Her inference from the worst cases (not measured): the lost answers have different row counts
from the reference where run 1 had the right count, i.e. wrong substance, not formatting.
Also noted: run 2's first pass is an outlier on lenient (0.608 against 0.538, 0.532, 0.532);
cause not examined. Her reproduction of every figure in the result tables agrees to four
decimals on point estimates; intervals differ in the third decimal by generator.
**Statement that stands for the write-up:** on human questions, run 1 fixed form and left
substance flat; run 2 has the same strict accuracy within noise and lost some substance.
