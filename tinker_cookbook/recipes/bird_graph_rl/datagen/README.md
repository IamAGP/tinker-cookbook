# Amendments C checkpoint

C2 rebalanced and C3 new shallow shapes executed; exact current counts:

```json
{
  "step": "C2/C3 applied; replay next",
  "totals": {
    "enumerated_structures": 505,
    "kept_structures": 431,
    "kept_instances": 4982
  },
  "c2": {
    "training_shallow_share": 0.5003756574004508,
    "training_deep_share": 0.14951164537941397,
    "training_structure_min": 6,
    "training_structure_max": 10
  },
  "split_hops": {
    "train": {
      "0": 166,
      "1": 500,
      "2": 466,
      "3": 70,
      "4": 129
    },
    "heldout_instance": {
      "0": 33,
      "1": 100,
      "2": 93,
      "3": 14,
      "4": 24
    },
    "heldout_structure": {
      "0": 54,
      "1": 169,
      "2": 1000,
      "3": 1073,
      "4": 1091
    }
  },
  "moved_deep": 151
}
```

Next: independent replay, hints refresh, then append individually authored
questions in priority order, checkpointing after each batch. Earlier sections
below describe the previous revision. C1 withdraws the return-width concern.

# Amended data generation — checkpoints complete

A1–A3, B3, B4 implementation, regeneration/replay, B5, and the amended pilot are
complete. **B4 caveat:** generic aliases are eliminated and anchors are diversified,
but scalar-only results still account for 63.97%. No explicit
numeric quota for multi-column results was stated; further work should use natural
per-user/per-tag summaries rather than add redundant columns to scalar questions.

## Run

Use installed dependencies only, from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -o cache_dir=tinker_cookbook/recipes/bird_graph_rl/datagen/.pytest_cache tinker_cookbook/recipes/bird_graph_rl/datagen
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tinker_cookbook.recipes.bird_graph_rl.datagen.generate --attempts 48
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tinker_cookbook.recipes.bird_graph_rl.datagen.hints
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tinker_cookbook.recipes.bird_graph_rl.datagen.pilot
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tinker_cookbook.recipes.bird_graph_rl.datagen.inspect
```

The final run used seed 20261003 and at most 48
parameter sets per structure. The smaller sampling budget was selected to complete
the amendment turn within its time limit; all instance/structure targets were met.
The tiny `--limit-structures` smoke run failed A3 because it had no surviving
four-hop component and extras; the splitter deliberately does not relax A3.
An outdated subtype unit-test assertion initially failed after count semantics
changed to distinct entities; it was corrected. Final **19 unit tests pass**.

Connection settings are read through python-dotenv from repository-root `.env`,
using only BIRD_NEO4J_* variables. They are never logged or copied. Every query
runs in an explicit READ_ACCESS transaction and rolls back. Mutating clauses and
procedures are rejected. No evaluation artifacts were read. No dependencies were
installed, no files outside datagen were edited, and this agent did not commit or
push. Per-query diagnostics remain in ignored `out/debug.log`.

## Final counts (computed from report.json)

**401 structures, 4654 instances**
from 465 natural canonical candidates. Short-hop
structures: 14.71%; all hop counts represented.

| Hops | Structures | Instances |
|---|---:|---:|
| 0 | 11 | 127 |
| 1 | 48 | 567 |
| 2 | 131 | 1559 |
| 3 | 102 | 1157 |
| 4 | 109 | 1244 |

Structure splits: {"heldout_structure": 80, "train": 321}.
Instance splits: {"heldout_instance": 635, "heldout_structure": 936, "train": 3083}.
Novelty tags: {"novel_combination": 60, "novel_component": 20}.

B3 removed **104 structures**:
aggregation membership {"count": 82, "sum": 22};
extras membership {"HAVING-style post-filter": 22, "difference of two aggregates": 22}.
Exact directed canonical path counts are in `out/naturalness.json` and
`report.json`. Multiplicity-counting count/group/HAVING structures and score minus
absolute-score totals were rejected. Distinct-entity groupings and minimum-count
filters have their own signatures and ordinary visitor intents. The entire
old difference-of-aggregates component is absent; that loss is explicit rather
than hidden. Every retained structure includes its one-sentence intent.

Anchors by instance: {"date": 891, "title": 830, "id": 731, "name": 1563, "badge": 512, "range": 127}.
Numeric-ID anchor share: **15.71%**.
Return shape counts: {"1 columns": 2977, "2 columns": 1677}.
Single-column share: **63.97%**; single-column `value` alias
share: **0.00%**. Aggregate aliases describe the
measurement; entity lists/groupings include names or text and measurements/counts.
These percentages count instances. Filter-use denominators differ from anchor
counts; see the explicit filter-use audit below.

Rejections: {"execution_error": 0, "runtime_over_5s": 2, "row_count": 1438, "all_null": 842, "cut_boundary_tie": 629, "unstable_result": 0, "ambiguous_name": 0, "trivial_constant_answer": 1461, "parameter_sampling_error": 1, "no_sampled_parameters": 2}.
The final run had no Cypher execution errors. Slow instances and the sampling
failure were rejected; their structures/parameter values and error codes are in
`debug.log`. No rejected result was padded into the target count.

## Scientific split and canonicalisation

Filters are (label, kind), aggregation is (kind, target label), grouping is a label.
Property names and parameter values do not enter the signature. Branch ordering
and variable names are canonicalised by directed-graph permutations; all stored
edges use schema direction. Question/Answer labels become Post plus subtype
filters. Signature scope is generated queries only, as A4 requires.

A3 holds out an entire extras kind, a canonical four-hop pattern, and an independent
aggregation/extras pairing. Exact selected components: {"extra": "negation", "four_hop_path": "{\"edges\":[[0,\"ACCEPTED\",1],[2,\"OWNS\",1],[2,\"OWNS\",3],[3,\"TAGGED\",4]],\"labels\":[\"Post\",\"Post\",\"User\",\"Post\",\"Tag\"]}", "aggregation_extras_pairing": "[[\"count distinct\", \"PostHistory\"], [\"HAVING-style post-filter\"]]"}.
Every held-out tag is recomputed from the actual post-filter training component
union; `unseen_components` records the proof. About 20% is held out within hop
strata, subject to mandatory component exclusion. Up to two distinct complete
parameter dictionaries for each training structure go to heldout_instance, leaving
at least two training examples.

Ordinary site statistics deduplicate **entity IDs before aggregation**, rather
than sum distinct numeric measurements. Thus different posts with equal scores
both contribute. Count groupings count distinct associated entities, not repeated
matches. Bounded Cypher 25 REPEATABLE ELEMENTS permits logical conditions to reuse
a stored fact; repeated matches are still deduplicated. This was checked against
[the official Cypher 25 manual](https://neo4j.com/docs/cypher-manual/25/patterns/repeatable-node-and-relationship-paths/)
and on the live installed graph. Official [driver transaction documentation](https://neo4j.com/docs/python-manual/current/transactions/)
was used for READ_ACCESS, explicit transactions and server timeouts.

Primary truncation ties are rejected with a separate k+1 probe; identity is the
last ordering key. All rows are preserved up to the allowed cap; oversized results
are rejected. Answers compare as order-insensitive multisets. Column names remain
in the artifacts for readability; B2 requires downstream scoring to ignore them.
A graph change invalidates saved answers and name/tie proofs. Runtime fields and
load-dependent timeout acceptance cannot be deterministic; other sampling, IDs,
signatures and splits are deterministic on an unchanged graph.

## Checkpoint (d), (e), (f)

Exhaustive artifact checks and **129 independent live replays**
passed. They cover 32 patterns, every retained rendering
mode, all hop counts, and all 60 pilot queries.

Hints: 4289 present, 365 absent,
**92.16% coverage**. Assignment and text are deterministic from
instance ID and query parts, without any evaluation inputs. The original
Posts.CreaionDate spelling was verified in the schema export code; other creation
dates use CreationDate. Hints also clarify stored counters, text previews,
missingness, percentages and per-user differences. Pilot records still contain
only instance_id and question: no hint field is added to the pilot itself.

The amended pilot has **60 questions on distinct structures** and
uses ordinary words, no return aliases or query syntax. Each question was authored
separately; exact subjects/filters are bound from verified instances. Quoted real
names and titles are exempt from syntax-word checks, since renaming them would
change the question. Post/answer/comment previews are specified where the query
returns a text prefix. Bindings and small result previews are in pilot_review.jsonl.

## Next work / unresolved questions

See QUESTIONS.md. Full stage-B generation is not performed. Before scaling,
independently review naturalness, entity-grouping intent, and question ambiguity;
verify that preview wording, distinctness, dates and snapshot counters agree with
the query; and increase naturally useful multi-column summaries. Do not scale this
pilot by replacing parameters in its sentences. Full-run objects/hints are ready
for that next stage, but pilot grammar and human plausibility still need an
independent review rather than a claim of statistically verified naturalness.

Filter-use audit: {"year/date range": 1093, "equality on name": 2905, "IS NOT NULL": 170, "equality on id": 731, "label test:Answer": 1226, "label test:Question": 1130, "string CONTAINS": 103, "numeric range": 127, "string STARTS WITH": 115, "IS NULL": 204}; numeric-ID share of all filter uses: 9.37%.

## Checkpoint: C2/C3 replay complete

All 133 independent saved-instance executions matched, covering 32 paths and all retained rendering modes, including each new C3 shape and the existing 60 pilot bindings. Hints refreshed: 4,594 / 4,982 instances. One new test initially asserted a literal count(DISTINCT) implementation; the query actually deduplicates identities before count(*), so the assertion was corrected to that equivalent implemented form. Unit suite rerun next. Step 2 queue is persisted; all training instances come first, round-robin by structure to prevent consecutive paraphrase writing.

## Question batch checkpoint

{"batch_size": 100, "batch_start": 0, "questions_by_split": {"train": 100}, "questions_total": 100}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Next: continue the persisted training queue before either held-out split.
