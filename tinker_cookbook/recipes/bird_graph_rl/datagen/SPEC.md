# Data generation spec — stage A (query-first)

**Why query-first.** The 186 evaluation questions cover only 64 distinct query structures and
never join more than three tables. Writing questions first and hoping they cover the space
produced template memorisation on an earlier project. Here the *query structure* is enumerated
deliberately, each query is executed so its answer is ground truth by construction, and the
natural-language question is written afterwards (stage B, separate).

## Hard rules
1. **Never read** anything under `gold/` in object storage, `reference_answers.json`, the BIRD
   question files, or `~/bird_rl_runs/`. The evaluation set must stay unseen by the generator.
2. Read-only against the graph: use read transactions only. Connection settings come from the
   repo-root `.env` (`BIRD_NEO4J_URI`, `BIRD_NEO4J_USER`, `BIRD_NEO4J_PASSWORD`) via
   `python-dotenv`. Never print, log or write those values.
3. Do not `git commit` or `git push`. Do not modify files outside `datagen/`.
4. Use the repo interpreter `.venv/bin/python`. No new dependencies.
5. Everything deterministic under a fixed seed.

## The graph
Schema, property names, types and traps: `../DATA_HANDOFF.md` §3–4 and the `SYSTEM_PROMPT` in
`../baseline_eval.py`. Cypher 25. Datetimes are LOCAL DATETIME (`x.creationDate.year = 2010`),
`Vote.creationDate` is DATE, NULLs are absent, `displayName` is not unique, `ON_POST` is used by
both Comment and Vote.

## What to build (`datagen/`)
- `structures.py` — enumerates **query structures** and gives each a stable `structure_id` and a
  canonical `signature`. A structure is the tuple:
  `(path, filters, aggregation, grouping, ordering, extras)` where
  - `path`: ordered node-label / relationship-type sequence, 0 to 4 hops, valid in the schema
    (include self-joins such as Answer→Question, Post→LINKS_TO→Post, and two-branch patterns
    such as User→Post and User→Badge);
  - `filters`: multiset of filter kinds — equality on id/name, numeric range, year/date range,
    string CONTAINS / STARTS WITH, IS NULL / IS NOT NULL, label test (Question/Answer);
  - `aggregation`: none, count, count distinct, sum, avg, min, max;
  - `grouping`: none or group-by key;
  - `ordering`: none, order-by, top-k (LIMIT k), argmax/argmin (LIMIT 1);
  - `extras`: subset of {existence (`EXISTS {}`), negation, ratio/percentage, difference of two
    aggregates, comparison between two named entities, HAVING-style post-filter (`WITH … WHERE`)}.
  Two queries share a structure iff their signatures are equal; parameter values never enter it.
- `generate.py` — for each structure, samples parameter values **from the graph** (seeded),
  renders Cypher, executes it, and keeps an instance only if all hold:
  1. it runs without error in ≤ 5 s;
  2. 1 ≤ rows ≤ 200, and not every value is NULL;
  3. deterministic: for top-k / argmax, the k-th and (k+1)-th sort keys differ (no tie at the
     cut); `ORDER BY` has a total order or the result is compared as a set;
  4. unambiguous naming: a `displayName` used as a filter must match exactly one user;
  5. not trivial: the same structure does not return the identical answer for every sampled
     parameter set.
  At most 12 instances per structure, with distinct parameter values.
- `split.py` — assigns each **structure** (not instance) to `train` or `heldout_structure`
  (about 80/20, seeded, stratified by hop count), so the held-out set contains only structures
  the model never trained on. Also emits a third set, `heldout_instance`: unseen parameter
  values for *training* structures.
- `*_test.py` — colocated unit tests (no database): signature stability, signature equality /
  inequality cases, split is by structure and reproducible under the seed.
- `README.md` — how to run, what was produced, counts.

## Output (`datagen/out/`, gitignored — create `datagen/.gitignore`)
- `structures.jsonl` — `structure_id, signature, hops, n_instances, split`.
- `instances.jsonl` — `instance_id, structure_id, split, hops, cypher, params, n_rows,
  rows (all, ≤200), runtime_ms`.
- `report.json` — counts by hop, by aggregation, by extras; rejection counts per filter rule;
  totals.

## Targets
≥ 150 distinct structures spanning 0–4 hops (not more than 35% of them at ≤ 1 hop),
≥ 1,500 kept instances. If a target cannot be met, say why in `README.md` with the rejection
counts — do not pad with near-duplicate structures.

## Pilot of stage B (small, to validate the format only)
For 60 instances spread across hop counts, write one natural-language question each into
`out/pilot_questions.jsonl` (`instance_id, question`). A question must be answerable from the
Cypher's result alone, must name the exact return columns asked for, must not mention labels,
relationship types or property names, and must not be a paraphrase template (vary form).

## Report back
Final message: the counts from `report.json`, the three hardest design choices you made and
why, anything in this spec you think is wrong, and what would break if stage B were scaled to
all instances.

## Amendments (2026-10-03, from review by the Fireworks agent) — binding
- **A1 Uniform granularity.** A signature records the *kind* and the *label it applies to*, never
  the property: filters are `(label, kind)`, aggregation is `(kind, target label)`, grouping is
  `(key label)`. So `sum(score)` and `sum(viewCount)` on Post share a structure; a year filter on
  Post and one on User do not.
- **A2 Canonical forms, unit-tested.** Branch order in multi-branch patterns is sorted; each
  relationship is written in its schema direction regardless of how the query traverses it;
  `:Question` / `:Answer` is canonicalised as `:Post` plus a label filter, so the two spellings
  of the same query share one signature.
- **A3 Two kinds of held-out structure.** `split.py` must additionally hold out some
  **components entirely** from training — at least one `extras` kind, one 4-hop path, and one
  (aggregation, extras) pairing — and tag every held-out structure as `novel_combination` (all
  of its components appear in training structures) or `novel_component` (at least one never
  does). Report counts for both. An earlier project found the first learnable and the second
  not; this split is the main scientific figure, so it must be exact.
- **A4 Scope note.** Signatures are defined only for generated queries. Nothing here classifies
  the evaluation questions or model-written queries by structure.
- **A5 Stage-B hints are undecided.** Do not invent a hint field in the pilot; write questions
  only. (Evaluation prompts carry a hint; whether generated ones should is an open decision.)

## Amendments B (2026-10-03, after reading the pilot) — binding; B1 and B2 correct errors in this spec
The pilot followed the spec faithfully and the result is unlike anything a person would ask.
Two of the causes are rules written above; they are withdrawn here.

- **B1 Vocabulary (replaces "must not mention labels, relationship types or property names").**
  Use the domain's ordinary words: user, post, question, answer, comment, vote, badge, tag,
  reputation, score, view count, favourite count, display name, title, location, age, and so on.
  Do **not** invent synonyms ("member", "standing points", "contribution", "remark"). What stays
  forbidden is query syntax: relationship type names in capitals, camelCase identifiers, label
  syntax, and the words "node", "edge", "relationship", "route", "connection", "path".
- **B2 No output-column instructions (replaces "must name the exact return columns").** A
  question says in plain words what is wanted ("list the titles", "how many", "which user").
  It never names an alias such as `value` or `entity_id`. Scoring ignores column names.
- **B3 Naturalness is decided per structure, before the split.** Keep a structure only if it has
  a one-sentence plain-English intent that a visitor to a Q&A site could plausibly ask. Drop
  structures whose only honest reading is counting graph paths with multiplicity ("how many
  routes from X through … to …"). Write the intent sentence into `structures.jsonl`. Report what
  was dropped **by component** (path, aggregation, extras), so a whole component class cannot
  disappear unnoticed. Re-run the split after filtering; A3 still applies to what remains.
- **B4 Anchors and return shapes must vary.** Measured on the current output: 78.7% of filter
  uses anchor on a numeric id and 59.9% of instances return a single column aliased `value`.
  Anchor instead on a unique display name, a post title, a tag name, a badge name, a year or a
  date range wherever the structure allows; keep numeric ids to a minority. Return what a person
  would want — names, titles, dates, counts, averages, percentages — with semantically named
  columns, not one fixed alias pair.
- **B5 Hints.** About 92% of instances carry a hint in the form "X refers to Y; …", written
  deterministically from the query's own parts (which stored field a phrase maps to, how a
  percentage or difference is computed). Use the source-style field names listed in
  `../DATA_HANDOFF.md` where they differ from graph property names. The rest carry none.
- **B6 Question writing at scale must not be a template.** One question per instance, individually
  worded; vary form, length and register; no shared sentence skeleton across instances of the
  same structure beyond what the meaning forces.

Redo the pilot (60 questions) under B1–B6 before scaling, and report how many structures B3 removed.

## Notes on amendments B (2026-10-03, from review)
- **B5's "about 92%" is the one statistic taken from the evaluation set**: 172 of its 186 prompts
  carry a hint. It describes the prompt *format*, not any question's content, and is declared as
  the single exception in `../PLAN.md`. B4's figures are measurements of the generated output
  only and must stay that way: "unlike the evaluation set" is a reason to redo a pilot, never a
  numeric target for anchors or return shapes.
- **B3 is a model's judgement and is audited by someone other than the generator** before the
  split is frozen: every dropped structure's intent sentence is read, and a sample of the kept
  ones, by a person or another agent. An independent check also compares the coarse shapes kept
  and dropped against the shapes people ask in a human-written question set from other databases.

## Amendments C (2026-10-03, from an independent measurement of human-written questions) — binding
Evidence: 6,601 human-written question–SQL pairs from BIRD's official filtered training split
(69 other databases; none is the evaluation database), classified by coarse shape by another
agent, 0 unclassified. This is *not* the evaluation set. Figures are relational hops (table
references minus one), an upper bound on graph hops.

- **C1 corrects B4 on return shapes.** People ask for a single column 83.9% of the time and two
  columns 12.1%. A single-column answer is normal; do **not** widen returns for variety. What was
  wrong in the first output was the fixed alias, not the width. Keep semantically named columns.
- **C2 Depth mix is a target taken from that human set, and is declared as one.** In it 21.4% of
  questions need 0 hops, 57.6% need 1, 16.8% need 2, 3.5% need 3 and 0.67% need 4 or more. The
  first output, computed from its files, had 853 of 5,590 instances (0.153) at ≤1 hop and 2,925
  (0.523) at 3–4 hops. Required of the **training** split:
  - at least half of its instances are at ≤1 hop, and at most 15% are at 3–4 hops;
  - **every training structure has between 6 and 12 instances.** Do not meet the floor by raising
    the per-structure cap on shallow structures — a few structures practised many times is the
    template-memorisation setup. Meet it by adding shallow structures (C3 adds several) or by
    accepting a smaller training set;
  - consequently only a limited number of deep structures can be in training. Choose them so the
    shares above hold, and move **all other deep structures to the held-out split**, where A3's
    tags still apply. A deep structure with one training instance is not "retained"; it is noise.
  The training set will be smaller than the earlier 1,500 target; that is accepted. Report the
  resulting counts by hop for each split.
- **C3 Shapes people ask that the structure tuple should express:** the n-th ranked item
  (`ORDER BY … SKIP n LIMIT 1`), conditional aggregates (counting or summing under a condition
  inside one query), and a DISTINCT projection as opposed to `count(DISTINCT …)`. A `LIMIT`
  without an order stays excluded: it is non-deterministic.

## Notes on amendment C2 as realised (2026-10-03, from the Fireworks agent's join of the files)
- The floor and cap in C2 are met approximately, not to the letter, and are to be read as "about":
  on the 600 training questions 0.493 are at ≤1 hop (floor 0.50) and 0.158 at 3–4 hops (cap 0.15);
  on the 300-question file the first run reads, 0.500 and 0.160. The run itself drew 0.506 and
  0.175 over its first 160 groups. The data is not regenerated for a difference of a few questions.
- "Between 6 and 12 instances per training structure" binds **instances**, not questions. Questions
  per training structure are 4–5 in the 600 and 2–3 in the 300-question file.
- **Consequence of moving deep structures to held-out:** the held-out-structure question set is far
  deeper than training (0.600 at 3–4 hops against 0.158), so any comparison of seen and unseen
  structures must be made at matched hop count.

## Amendment D (2026-10-03) — a second training set whose mix follows human-written questions
**Why.** The first run improved a lot on generated questions and little on human ones. Measured
before that result, on 6,601 human-written questions from another benchmark split (69 other
databases): people mostly ask plain lookups and counts, while the first training set was 48.7%
sum / avg / min / max. This amendment builds a second **training** set; nothing held out changes.

**Frozen — do not modify, regenerate or re-split:** every existing file in `out/`, every existing
instance id, the 264 held-out-instance questions, the 360 held-out-structure questions and the
split and novelty tags of every existing structure. The second training set lives in `out/v4/`.

**Build `out/v4/questions_v4_train.jsonl`: 320 training questions** (`instance_id`, `question`),
with `out/v4/instances_v4_train.jsonl` holding their instances in the existing format (hints per
B5; rules B1, B2, B6 for wording). Target mix, taken from that human set — aim within about three
points on each line and report what was achieved:
- aggregation: none 55% · count 25% · sum 7% · count distinct 3% · avg 3% · max 2% · min 1% ·
  more than one aggregate 5%
- ordering: none 83% · argmax or argmin (top 1) 14% · top-k 1% · n-th ranked under 1% ·
  order with no limit at most 1%
- grouping: about 10% of questions
- extras: none 72% · distinct projection 9% · ratio 8% · conditional aggregate 8% · negation 3% ·
  comparison of two named entities 2% · having 1% · existence 1%
- returned columns: one 84% · two 12% · three or more 4%
- depth: about 70% at ≤1 hop, about 20% at 2 hops, about 10% at 3–4 hops

**How to reach it.** Reuse existing training structures and instances where they fit. Add **new
training structures** where the mix needs them — mostly plain lookups and counts at 0–2 hops —
each verified by execution exactly as before. Constraints on anything new: its signature must
not equal that of any held-out structure, and it must not use any component that the split holds
out entirely (the `unseen_components` of novel-component structures); otherwise the held-out
tags would stop meaning what they say. Keep at most 5 questions per structure and no question
that also appears in a held-out set.

**Report** (`out/v4/report.json` and the README): achieved shares beside each target, computed;
counts of reused and new structures; and explicit checks that no v4 training structure equals a
held-out signature and that no held-out component was introduced.
