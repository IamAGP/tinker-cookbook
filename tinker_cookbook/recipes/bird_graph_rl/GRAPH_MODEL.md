# Graph model: BIRD `codebase_community` → Neo4j

v1 — 2026-09-20. Status: **profiled, exported and loaded; see JOURNAL.md for measured counts.**
Target: Neo4j Community Edition 2026.07.1, default language Cypher 25, store format `aligned`.

Source: the `codebase_community` SQLite database from BIRD-SQL (CC BY-SA 4.0), a Stack
Exchange (stats) data dump: 8 tables — `users, posts, comments, votes, badges, tags,
postLinks, postHistory`. Schema and 49 gold question/SQL pairs were read from the official
`bird-bench/mini_dev` repository.

Every claim below is tagged **[doc]** (read in Neo4j's official docs this session),
**[local]** (checked on the local instance / CLI), **[data]** (read from BIRD's schema or
gold SQL), or **[inference]** (a design judgement, open to challenge).

---

## 1. What Community Edition allows (this constrains the design)

| Capability | Community | Consequence |
|---|---|---|
| Property **uniqueness** constraints (node + relationship, composite) | yes **[doc]** | Used for every business key. Each creates a backing range index **[doc]**. |
| Property **existence**, **type**, **key** constraints | Enterprise only **[doc]** | "NOT NULL" and type guarantees must be enforced in the ETL validation step instead. |
| Multiple user databases | no **[doc]** | One graph at a time in the `neo4j` database. Import overwrites it. |
| Role-based access control | no **[doc]** | No read-only DB user. The agent's tool must enforce read-only itself (see §7). |
| Online backup | no **[doc]** | Use offline `neo4j-admin database dump`; keep the dump in object storage. |
| `block` store format / constraints created *during* bulk import | Enterprise only **[doc]** | Create constraints and indexes *after* import. |
| `neo4j-admin database import full` reading from **S3 URIs** | **no** **[local]** — `--help` advertises it, but a dry run fails with `No storage system found for scheme: s3`; only the `neo4j-cloud` abstraction jar ships, no S3 provider | Load with `LOAD CSV` over presigned HTTPS URLs instead (§6). An earlier draft of this table claimed yes from the help text alone; the dry run disproved it. |

## 2. Nodes

| Label | Business key (unique) | From | Notes |
|---|---|---|---|
| `:User` | `userId` | `users` | Includes the system user `userId = -1` ("Community"). |
| `:Post` (+ `:Question` / `:Answer`) | `postId` | `posts` | Secondary label from `PostTypeId` (1 → Question, 2 → Answer). `postTypeId` is also kept as a property. |
| `:Comment` | `commentId` | `comments` | |
| `:Vote` | `voteId` | `votes` | Intermediate node — see §4. |
| `:PostHistory` | `postHistoryId` | `postHistory` | Intermediate node — see §4. |
| `:Tag` | `tagId`, and `tagName` | `tags` | Two independent uniqueness constraints. |
| `:Badge` | `name` | distinct `badges.Name` | The badge *kind*. Each award is an `EARNED` relationship. |

Property naming: camelCase properties, PascalCase labels, UPPER_SNAKE relationship types
**[doc: Cypher style guide]**. Source typos are fixed and recorded here so gold-SQL
translation stays traceable: `CreaionDate → creationDate`, `LasActivityDate → lastActivityDate`.

## 3. Relationships

| Pattern | From | Properties |
|---|---|---|
| `(:User)-[:OWNS]->(:Post)` | `posts.OwnerUserId` | — |
| `(:User)-[:LAST_EDITED]->(:Post)` | `posts.LastEditorUserId` | — (`lastEditDate` stays on the Post) |
| `(:Answer)-[:ANSWERS]->(:Question)` | `posts.ParentId` | — |
| `(:Question)-[:ACCEPTED]->(:Answer)` | `posts.AcceptedAnswerId` | — (not a declared FK in the DDL **[data]**, but semantically one **[inference]**) |
| `(:Post)-[:TAGGED]->(:Tag)` | parsed from `posts.Tags` (`<a><b>`) | — |
| `(:Tag)-[:HAS_EXCERPT]->(:Post)` | `tags.ExcerptPostId` | — |
| `(:Tag)-[:HAS_WIKI]->(:Post)` | `tags.WikiPostId` | — (undeclared FK **[data]**) |
| `(:Post)-[:LINKS_TO]->(:Post)` | `postLinks` (pure join table) | `postLinkId`, `linkTypeId`, `creationDate` |
| `(:User)-[:WROTE]->(:Comment)-[:ON_POST]->(:Post)` | `comments` | — |
| `(:User)-[:CAST]->(:Vote)-[:ON_POST]->(:Post)` | `votes` | — |
| `(:User)-[:MADE]->(:PostHistory)-[:REVISES]->(:Post)` | `postHistory` | — |
| `(:User)-[:EARNED]->(:Badge)` | `badges` | `badgeId`, `date` |

`ON_POST` rather than `ON`: `ON` is a Cypher keyword (`CREATE INDEX … ON`), which invites parse confusion for a model writing queries.

## 4. Design decisions, and the anti-pattern each one avoids

1. **Join table → relationship.** `postLinks` has two FKs to the same table plus attributes;
   Neo4j's guide maps exactly this to a relationship with properties **[doc]**.
2. **Delimited column → relationships.** `posts.Tags = '<bayesian><prior>'` is a
   denormalized multi-value column. It becomes `TAGGED` relationships and the raw string is
   dropped **[doc: "duplicate data in denormalized tables … pulled out into separate nodes"]**.
   A gold SQL that tests `Tags = '<humor>'` (exactly one tag) stays expressible as
   `COUNT { (p)-[:TAGGED]->() } = 1`. **Build-time check required:** every parsed tag must
   exist in `tags`; unverified until the ETL runs.
3. **Event with 3 participants → intermediate node, not a relationship.** A vote links a
   user, a post and a type, and `votes.UserId` can be NULL. Modelled as a `User→Post`
   relationship, every anonymous vote would vanish. Same reasoning for `Comment` and
   `PostHistory` (they carry text and an optional user). **[inference]**, consistent with
   Neo4j's intermediate-node pattern.
4. **Technical primary keys are KEPT — deliberate deviation.** The guide says drop
   system-generated ids **[doc]**. Here BIRD questions address rows by id ("User No.3025",
   "vote No.6347") **[data]**, so the ids are business keys. They get uniqueness constraints.
5. **Lookup ints: label where it drives traversal, property where it is only a filter.**
   `PostTypeId` 1/2 → `:Question`/`:Answer` labels (token-lookup index makes label scans
   cheap **[doc]**). `VoteTypeId`, `PostHistoryTypeId`, `LinkTypeId` stay integer properties:
   BIRD ships no lookup table for them, so inventing names would add information that is
   not in the source. **[inference]**
6. **Denormalized counters are kept verbatim** (`answerCount`, `commentCount`,
   `favoriteCount`, `Tag.count`, `User.upVotes`). They are snapshot values from the source
   and may disagree with countable rows in a sampled dump. Gold answers read them, so they
   must not be "repaired". **[inference]**
7. **No phantom users.** `OwnerDisplayName`, `UserDisplayName`, `LastEditorDisplayName`
   exist for rows whose user was deleted. They stay as properties on the Post / Comment /
   PostHistory; no `:User` node is fabricated.
8. **NULLs and empty strings are not stored** **[doc: "graphs don't require storing nulls"]**
   — import with `--ignore-empty-strings=true` **[local]**.
9. **Dates are native temporal properties, not date nodes.** `'2010-07-19 19:12:12.0'` →
   `LOCAL DATETIME`; `votes.CreationDate` → `DATE`. Neo4j's modeling-tips page suggests
   date *nodes* for range-heavy workloads **[doc]**. I am **not** following that: the gold
   SQL only does year extraction, min/max and exact-timestamp equality **[data]**, which a
   range-indexed temporal property serves without a calendar tree. **[inference]**
10. **Dense nodes.** Expected hubs: `User{-1}`, popular `:Tag`s, common `:Badge`s. At this
    scale that is thousands to tens of thousands of relationships per hub, not millions
    **[inference — row counts not yet measured]**. No fan-out mitigation planned.

## 5. Constraints and indexes

See `schema.cypher`. Index choices follow the predicates in the 49 gold SQLs **[data]**:
`DisplayName` (12 uses), `Title` (8), `TagName`, `Name` (badge), plus equality on comment
and post-history text, `LIKE '%…%'` on title, and range filters on `Score`, `ViewCount`,
`Reputation`, dates.

- **Range index** → equality, range, `STARTS WITH`, `IN`, `IS NOT NULL` **[doc]**.
- **Text index** → equality, `STARTS WITH`, `CONTAINS`, `ENDS WITH`; strings only **[doc]**.
  Used for `Post.title` (substring search) and for long free-text equality
  (`Comment.text`, `PostHistory.text`).
- Deliberately **not** indexed at first: low-cardinality counters (`commentCount`,
  `answerCount`, `age`). Decide with `PROFILE` after load rather than by guess.
- Open item: maximum indexable string length for range vs text indexes was **not** found
  in the docs read this session. Must be checked before indexing `text`/`body` fields.

Indexes affect speed only. They cannot leak answers to the model.

## 6. Load path (nothing staged on the laptop) — as executed

1. `etl/lambda_profile.py` (one-off Lambda) reads the SQLite file from object storage and
   writes `profile.json`: row counts, FK orphans, NULL rates, lookup distributions, tag-parse
   coverage, datetime-format violations, text sizes.
2. `etl/lambda_export.py` writes one CSV per label / relationship source plus
   `manifest.json` (the reconciliation target). Orphaned FKs are dropped from relationship
   files; the node is kept.
3. `etl/load_csv_from_s3.py` creates the 7 node-key uniqueness constraints, then streams each
   CSV with `LOAD CSV WITH HEADERS FROM <presigned https url>` inside
   `CALL (row) { … } IN TRANSACTIONS OF 5000 ROWS`. Two settings matter:
   - `db.import.csv.legacy_quote_escaping=false` **[local: not dynamic, needs restart]** —
     the default treats `\"` as an escaped quote; post bodies are full of LaTeX backslashes.
   - presign against the **regional** S3 endpoint: the global endpoint answers `307` for a
     newly created regional bucket and `LOAD CSV` does not follow it **[local: curl 307 vs 206]**.
4. Run `schema.cypher` → all indexes `ONLINE` → reconcile counts against `manifest.json`.
5. `neo4j-admin database dump` → object storage, so the graph is reproducible.

## 7. Things that are easy to forget (the experiment depends on them)

1. **SQL and Cypher disagree silently.** SQLite `LIKE` is case-insensitive for ASCII;
   Cypher `CONTAINS` is case-sensitive. Integer division, `CAST(... AS REAL)`, NULLs in
   aggregates, and **tie-breaking in `ORDER BY … LIMIT 1`** can all differ. Every gold
   answer needs an SQLite-vs-Neo4j equality check, and tied questions need an audit.
2. **Gold SQL quality.** In the mini-dev file several "posts by X" questions are answered
   through `postHistory.UserId`, and "most valuable post in 2010" filters on the *user's*
   creation date **[data]**. BIRD released a corrected dev set in Nov 2025 **[doc: BIRD site]**;
   whether these specific items were fixed is **unchecked**. Decide up front whether the
   reward targets the executed gold-SQL answer (BIRD-comparable) or the question's plain
   meaning. The graph above can reproduce either.
3. **Agent safety on Community Edition.** No RBAC, and the instance currently has
   `db.transaction.timeout = 0s` and `db.memory.transaction.max = 0B` (both unlimited)
   **[local]**. Before any rollout: set a timeout and a memory cap (both dynamic settings
   **[local]**), make the tool use read transactions only, and consider
   `dbms.databases.default_to_read_only=true` after import **[local: present in neo4j.conf]**.
4. **Cypher 25 is this instance's default language [local].** Gold Cypher must be written
   and verified in it; a base model's prior is mostly older Cypher.
5. **49 questions is an eval set, not a training set.** Same trap as before: generated
   training questions create template memorization. Keep BIRD's human questions as a
   held-out eval that the generator never sees.
6. **Disk.** The laptop has ~15 GB free. Post bodies and revision text dominate store size;
   the Neo4j store will likely exceed the 481 MB SQLite file **[inference]**. Measure after
   import; dropping `PostHistory.text` is the first lever.
7. **Attribution.** BIRD is CC BY-SA 4.0 and the underlying content is Stack Exchange
   user content; any published graph, dump or blog needs attribution and share-alike.

## 8. Open questions

- Reward target: executed gold-SQL answer, or corrected semantics? (§7.2)
- Keep `PostHistory.text` and `Post.body` (largest properties), or drop to save disk?
- Approve the one-off compute job for row counts + CSV export?
