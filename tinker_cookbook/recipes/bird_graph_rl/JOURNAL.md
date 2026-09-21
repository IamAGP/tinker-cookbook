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
