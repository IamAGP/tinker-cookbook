# Data handoff: the `codebase_community` knowledge graph

**Audience:** any agent or person about to train or evaluate a model against this graph
(including RL fine-tuning done from another repo). Read this before touching the data.
**Written:** 2026-09-21. Facts below were measured on 2026-09-20/21; re-verify anything
marked *(verify)* before relying on it. Full evidence trail: `JOURNAL.md`. Design rationale:
`GRAPH_MODEL.md`. Concrete bucket names and credentials are **not** in this file (public
repo) — see `LOCAL_RESOURCES.md`, which is gitignored and kept only locally.

---

## 1. What this is, in one paragraph

One database from the **BIRD-SQL** text-to-SQL benchmark — `codebase_community`, a Stack
Exchange (statistics Q&A) data dump — re-modelled as a property graph and loaded into a
local **Neo4j Community Edition 2026.07.1** instance. BIRD supplies human-written questions,
gold SQL and difficulty labels for it. The intended task: a model answers those questions by
writing **Cypher** against the graph, scored against execution-verified reference answers.
License: BIRD is CC BY-SA 4.0 and the content is Stack Exchange user content — attribution
and share-alike apply to anything published.

## 2. Size (reconciled exactly against the source, zero mismatches)

| Nodes | | Relationships | |
|---|---|---|---|
| `:User` | 40,325 | `OWNS` (User→Post) | 90,574 |
| `:Post` (`:Question` 42,912 / `:Answer` 47,755 / 1,299 other) | 91,966 | `LAST_EDITED` (User→Post) | 44,605 |
| `:Comment` | 174,285 | `ANSWERS` (Answer→Question) | 47,749 |
| `:Vote` | 38,930 | `ACCEPTED` (Question→Answer) | 14,696 |
| `:PostHistory` | 303,155 | `TAGGED` (Post→Tag) | 117,633 |
| `:Tag` | 1,032 | `HAS_EXCERPT` / `HAS_WIKI` (Tag→Post) | 595 / 596 |
| `:Badge` (badge *kind*) | 153 | `LINKS_TO` (Post→Post) | 11,098 |
| | | `WROTE` (User→Comment) | 171,450 |
| | | `ON_POST` (Comment→Post 174,249; Vote→Post 38,930) | 213,179 |
| | | `CAST` (User→Vote) | 3,425 |
| | | `MADE` (User→PostHistory) | 281,829 |
| | | `REVISES` (PostHistory→Post) | 303,114 |
| | | `EARNED` (User→Badge) | 79,851 |
| **Total** | **649,846** | **Total** | **1,380,394** |

## 3. Schema cheat-sheet

```
(:User {userId, displayName, reputation, creationDate, lastAccessDate, websiteUrl, location,
        aboutMe, views, upVotes, downVotes, accountId, age, profileImageUrl})
(:Post:Question|:Answer {postId, postTypeId, creationDate, score, viewCount, body, title,
        lastActivityDate, lastEditDate, communityOwnedDate, closedDate, answerCount,
        commentCount, favoriteCount, ownerDisplayName, lastEditorDisplayName})
(:Comment {commentId, score, text, creationDate, userDisplayName})
(:Vote {voteId, voteTypeId, creationDate(DATE), bountyAmount})
(:PostHistory {postHistoryId, postHistoryTypeId, revisionGuid, creationDate, text, comment, userDisplayName})
(:Tag {tagId, tagName, count})          (:Badge {name})
(User)-[:EARNED {badgeId, date}]->(Badge)      (Post)-[:LINKS_TO {postLinkId, linkTypeId, creationDate}]->(Post)
```
- Datetimes are native `LOCAL DATETIME`; `Vote.creationDate` is `DATE`. Year filter: `p.creationDate.year = 2010`.
- NULLs and empty strings are **absent**, not stored. Use `IS NULL` / `coalesce`.
- Source column typos were fixed: `CreaionDate → creationDate`, `LasActivityDate → lastActivityDate`.
  Gold SQL still uses the typo'd names.
- Constraints: uniqueness on every `…Id`, `Tag.tagName`, `Badge.name`, `LINKS_TO.postLinkId`,
  `EARNED.badgeId`. Indexes: 14 range + 2 text (`Post.title`, `Comment.text`). See `schema.cypher`.

## 4. Traps that will silently produce wrong answers

1. **`displayName` is not unique** — 35,644 distinct names over 40,325 users. "the user X"
   may be several people.
2. **91% of votes have no user** (35,505 of 38,930). That is why `Vote` is a node; never
   assume `(User)-[:CAST]->(Vote)` exists.
3. **Counters are snapshots, not derived.** `answerCount`, `commentCount`, `favoriteCount`,
   `Tag.count`, `User.upVotes` come verbatim from the source and can disagree with countable
   relationships (19 tags differ). Gold answers read the stored counters.
4. **"posts by X" means `OWNS`**, not `MADE→REVISES` (edit history). Joining through edit
   history multiplies rows: one question yields −1491 that way and −497 correctly.
5. **SQL vs Cypher semantics:** SQLite `LIKE` is case-insensitive, Cypher `CONTAINS` is not;
   integer division and `ORDER BY … LIMIT 1` tie-breaking can differ.
6. **`ON` was deliberately avoided** as a relationship type (Cypher keyword) → `ON_POST`.
7. A few FK orphans were dropped as relationships (node kept): comments→posts 36,
   postHistory→posts 41, others ≤6.
8. Default query language on the instance is **Cypher 25**.

## 5. Gold questions and reference answers

- **Use BIRD's Nov-2025 corrected dev release** (`birdsql/bird_sql_dev_20251106` on Hugging
  Face): **186 questions** for this database — 151 simple / 30 moderate / 5 challenging.
- Do **not** use the older mini-dev SQL as ground truth: of its 49 questions for this DB,
  the corrected release changed the SQL on 15 and **the executed answer on 8 (16%)**.
- All 186 corrected gold SQLs were executed on the original SQLite file: **0 errors, 0 empty
  results**. Results live in object storage as `gold/reference_answers.json` (rows capped at
  200 per question, plus full row count and an order-insensitive hash of all rows).
- Known fragile items: **Q669** (`LIMIT 1` with tied sort keys — tie-dependent);
  11 questions return >200 rows (up to 20,198) — score those by hash/row-count, not by
  listing; the corrected release still contains at least one logically doubtful item
  (Harvey Motulsky vs Noah Snyder sums views per edit-history row).
- **Graph fidelity check:** 5 of 5 hand-written Cypher queries reproduced SQLite's executed
  answer exactly (including both the wrong −1491 and the right −497). Gold **Cypher** for the
  full 186 does not exist yet.
- **186 questions is an evaluation set, not a training set.** A previous project on a
  different graph showed that generating training questions from templates yields template
  memorisation (in-distribution 0.95, held-out structure 0.23). Keep BIRD's human questions
  held out from whatever generates training data.

## 6. How to connect

- Bolt `bolt://localhost:7687`, user `neo4j`, database `neo4j`; password in `LOCAL_RESOURCES.md`.
- A Neo4j MCP server can be pointed at this instance (schema + read + write tools).
- **Community Edition has no role-based access control, and the instance currently has no
  query timeout and no transaction memory cap.** Before any automated rollouts: use
  read-only transactions in the tool, set `db.transaction.timeout` and
  `db.memory.transaction.max` (both dynamic), and consider
  `dbms.databases.default_to_read_only=true`. A single runaway query can hang the instance.
- One user database only (Community). Loading another graph replaces this one.

## 7. How to rebuild or restore

- **Restore (fast):** a `neo4j-admin database dump` of this graph (418 MB) is in object
  storage. Stop Neo4j → `neo4j-admin database load` → start.
- **Rebuild (≈6 min):** `etl/lambda_profile.py` → `etl/lambda_export.py` (one-off Lambdas,
  SQLite never leaves object storage) → `etl/load_csv_from_s3.py` → `schema.cypher`.
  Run the loader with `uv run --no-project --with boto3 --with neo4j python etl/load_csv_from_s3.py`.
- Requirements discovered the hard way: `db.import.csv.legacy_quote_escaping=false`
  (LaTeX backslashes), **regional** S3 endpoint for presigned URLs (global one 307-redirects),
  Community's `neo4j-admin import` **cannot** read `s3://`, and on Homebrew use
  `brew services stop` then `start`, never `restart`.
- The temporary Lambda, IAM role and log group are deleted after each use; recreate from the
  scripts. Nothing from the dataset is kept on the laptop except the Neo4j store itself.

## 8. Not done yet

Gold Cypher for the 186 questions · agent safety settings · reward function · training-question
strategy · choice of trainer/platform. Nothing in this folder is committed to git yet.
