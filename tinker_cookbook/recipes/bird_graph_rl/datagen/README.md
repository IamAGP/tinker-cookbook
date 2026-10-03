# Current checkpoint: requested held-out questions complete

Questions saved: 1224 total; train 600, heldout_instance 264, heldout_structure 360.

All 624 appended held-out instances were executed against the live graph and matched the saved answers. Replay failures: 0. All 21 unit tests pass. Frozen instance ids, split files and the original question prefix are byte-for-byte unchanged (SHA256 checks). No instances were regenerated. No evaluation set was read, no graph writes were issued, no dependencies were added, and no commit or push was made.

The exact selection and selected ids are in `out/heldout_structure_sample.json`. Selection rule: For every novel_component structure in structure_id order, select up to four instances with distinct canonical full params, ranked by SHA256(seed + colon + instance_id). For novel_combination, take the top-ranked instance per structure; sort structures within hop by structure_id, then cycle ascending available hop counts until the total sample reaches 360. No answer or question content is used to rank instances.

Sample question counts:

| Hops | novel_component | novel_combination | Total |
|---|---:|---:|---:|
| 0 | 14 | 2 | 16 |
| 1 | 4 | 15 | 19 |
| 2 | 64 | 45 | 109 |
| 3 | 47 | 45 | 92 |
| 4 | 80 | 44 | 124 |
| Total | 209 | 151 | 360 |

Novel-component coverage: all 53 structures. Measured per-structure selection distribution: {"2": 1, "3": 1, "4": 51}. Novel-combination coverage: 151 structures, each represented by its selected instance. Distinct parameter values mean distinct full canonical parameter dictionaries; this does not require every individual parameter field to differ. This interpretation is explicit and reproducible.

Language review corrected 34 individually identified sentences with awkward noun repetition or agreement. Only appended held-out text was refreshed atomically; the original training question prefix was preserved exactly. All 624 appended questions passed checks for forbidden domain substitutions, query terms, camelCase syntax and output-alias identifiers, excluding quoted graph literals.

Data-quality limitation in the frozen instances: 3 selected conditional aggregates have a threshold above their anchor range, forcing no qualifying items; 10 have a threshold no greater than the lower bound, so the additional condition is redundant. These remain faithfully worded because the owner froze instances and splits. Exact instance ids are listed in `out/heldout_question_audit.json`. This is an instance-generation limitation, not a failure of the new sampling rule. Execution and token audits do not prove that every natural-language question has a unique interpretation; independent language review is still the team's responsibility.

Tooling scope exception: the default pytest cache provider refreshed `.pytest_cache/v/cache/nodeids` at the repository root. Its modification time was measured after the run. The prior contents are unknown because no original snapshot was captured; no claim is made about a content difference, and it was not overwritten in an attempt to restore it. The final test command uses `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tinker_cookbook/recipes/bird_graph_rl/datagen`. Recipe artifacts and question changes are confined to datagen.

All requested question-writing work for this turn is complete. No further training questions are queued for writing under the current instruction. Earlier sections below describe prior priorities and checkpoints.

# Current checkpoint: amendments C, question batch six complete

{
  "step_1": "complete, independently replayed",
  "step_2": "six completed batches; continue training first",
  "structures": 431,
  "instances": 4982,
  "instances_by_split_hop": {
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
  "structures_by_split_hop": {
    "train": {
      "0": 17,
      "1": 50,
      "2": 47,
      "3": 7,
      "4": 14
    },
    "heldout_structure": {
      "0": 6,
      "1": 16,
      "2": 84,
      "3": 95,
      "4": 95
    }
  },
  "deep_structures_moved": 151,
  "novelty_counts": {
    "novel_component": 53,
    "novel_combination": 243
  },
  "c2": {
    "training_shallow_share": 0.5003756574004508,
    "training_deep_share": 0.14951164537941397,
    "training_structure_min": 6,
    "training_structure_max": 10,
    "training_shallow_percent": 50.038,
    "training_deep_percent": 14.951
  },
  "questions": {
    "written": 600,
    "by_split": {
      "train": 600,
      "heldout_instance": 0,
      "heldout_structure": 0
    },
    "training_remaining": 731,
    "novel_component_instances_required": 594,
    "heldout_structure_approx_target": 360,
    "priority_conflict": true,
    "audit": {
      "questions_total": 600,
      "questions_by_split": {
        "train": 600
      },
      "sample_replays": 26,
      "all_replays_match": true,
      "sample_modes": [
        "argmax",
        "avg",
        "bottom",
        "comparison",
        "conditional_count",
        "conditional_sum",
        "contains",
        "detail",
        "distinct",
        "entity_group",
        "entity_having",
        "exists",
        "label",
        "max",
        "min",
        "not_null",
        "nth",
        "null",
        "projection",
        "ratio",
        "starts",
        "sum",
        "top",
        "year"
      ]
    }
  },
  "validation": {
    "unit_tests_passed": 21,
    "instance_replays": 133,
    "question_replays": 26
  }
}

Next: individually author the remaining 731 training questions, beginning at queue index 600. Then write at least 200 held-out-instance questions. All 594 novel-component instances take priority over the approximate 360 total held-out-structure target; no novel-combination additions fit under that approximate target. The full priority queue is persisted. Do not rerun full generation while finishing this question set, because it would invalidate authored instance bindings.

Step 1 used the incremental C3 generator to preserve already verified instances and their identifiers. 30 new structures and 328 new instances were accepted. C3 rejection counts: {"all_null": 8, "cut_boundary_tie": 183, "row_count": 317, "trivial_constant_answer": 145}. Low-yield structures with fewer than six instances are entirely held out. Independent replays covered every retained rendering mode and all 32 pattern definitions. The new test initially failed because it required literal count(DISTINCT) rather than deduplication followed by count(*); it was corrected and all unit tests pass.

Cypher 25 syntax was checked against official documentation for [SKIP](https://neo4j.com/docs/cypher-manual/25/clauses/skip/), [RETURN DISTINCT](https://neo4j.com/docs/cypher-manual/25/clauses/return/), and [CASE](https://neo4j.com/docs/cypher-manual/25/expressions/conditional-expressions/), then executed against the live graph.

Question batches contain independently composed sentences, with helpers binding exact subjects, fields and literals. A grammar pass added articles, clarified missing-title fallbacks, changed user creation years to joining years, and made threshold-one nouns singular; quoted graph literals remain intact. Live executions verify the bindings and saved results, not subjective naturalness or unique interpretation. Independent language review remains with the team.

No evaluation data was read; graph operations used read transactions. No dependencies, commits, pushes or changes outside datagen were made. Earlier checkpoint sections below describe previous states.

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

## Question batch checkpoint

{"batch_size": 100, "batch_start": 100, "questions_by_split": {"train": 200}, "questions_total": 200}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Next: continue the persisted training queue before either held-out split.

## Question batch checkpoint

{"batch_size": 100, "batch_start": 200, "questions_by_split": {"train": 300}, "questions_total": 300}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Next: continue the persisted training queue before either held-out split.

## Question batch checkpoint

{"batch_size": 100, "batch_start": 300, "questions_by_split": {"train": 400}, "questions_total": 400}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Next: continue the persisted training queue before either held-out split.

## Question batch checkpoint

{"batch_size": 100, "batch_start": 400, "questions_by_split": {"train": 500}, "questions_total": 500}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Next: continue the persisted training queue before either held-out split.

## Question batch checkpoint

{"batch_size": 100, "batch_start": 500, "questions_by_split": {"train": 600}, "questions_total": 600}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Next: continue the persisted training queue before either held-out split.

Final completed-batch checkpoint: all 600 questions remain bound to their saved instances; 26 question-sample replays match. A final language correction makes user joining-year restrictions explicitly apply to the returned users, rather than the named anchor user. Next training queue index: 600. All 21 unit tests passed after the final generator reporting change.

## Held-out selection checkpoint

Current owner priority: stop training question writing; retain current ids and splits. Frozen hashes and original question prefix are in heldout_frozen.json. All held-out-instance instances appear first in heldout_question_queue.jsonl, round-robin by structure_id, with each structure’s instances sorted by the seeded hash. Measured held-out-instance count: 264. Then use the frozen heldout_structure_sample.json selection below.

```json
{
  "seed": "heldout-questions-20261003",
  "selection_rule": "For every novel_component structure in structure_id order, select up to four instances with distinct canonical full params, ranked by SHA256(seed + colon + instance_id). For novel_combination, take the top-ranked instance per structure; sort structures within hop by structure_id, then cycle ascending available hop counts until the total sample reaches 360. No answer or question content is used to rank instances.",
  "counts_by_novelty": {
    "novel_component": 209,
    "novel_combination": 151
  },
  "counts_by_hop": {
    "4": 124,
    "2": 109,
    "3": 92,
    "0": 16,
    "1": 19
  },
  "counts_by_novelty_hop": {
    "novel_component": {
      "0": 14,
      "1": 4,
      "2": 64,
      "3": 47,
      "4": 80
    },
    "novel_combination": {
      "0": 2,
      "1": 15,
      "2": 45,
      "3": 45,
      "4": 44
    }
  },
  "n_instances": 360,
  "n_structures": 204
}
```

Next: append individually authored held-out-instance questions, then the selected held-out-structure questions; checkpoint after each batch.

## Question batch checkpoint

{"batch_size": 100, "batch_start": 0, "questions_by_split": {"heldout_instance": 100, "train": 600}, "questions_total": 700}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Follow the latest owner priority and frozen queue for the next batch.

## Question batch checkpoint

{"batch_size": 100, "batch_start": 100, "questions_by_split": {"heldout_instance": 200, "train": 600}, "questions_total": 800}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Follow the latest owner priority and frozen queue for the next batch.

## Question batch checkpoint

{"batch_size": 64, "batch_start": 200, "questions_by_split": {"heldout_instance": 264, "train": 600}, "questions_total": 864}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Follow the latest owner priority and frozen queue for the next batch.

## Question batch checkpoint

{"batch_size": 100, "batch_start": 264, "questions_by_split": {"heldout_instance": 264, "heldout_structure": 100, "train": 600}, "questions_total": 964}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Follow the latest owner priority and frozen queue for the next batch.

## Question batch checkpoint

{"batch_size": 100, "batch_start": 364, "questions_by_split": {"heldout_instance": 264, "heldout_structure": 200, "train": 600}, "questions_total": 1064}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Follow the latest owner priority and frozen queue for the next batch.

## Question batch checkpoint

{"batch_size": 100, "batch_start": 464, "questions_by_split": {"heldout_instance": 264, "heldout_structure": 300, "train": 600}, "questions_total": 1164}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Follow the latest owner priority and frozen queue for the next batch.

## Question batch checkpoint

{"batch_size": 60, "batch_start": 564, "questions_by_split": {"heldout_instance": 264, "heldout_structure": 360, "train": 600}, "questions_total": 1224}

Questions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Follow the latest owner priority and frozen queue for the next batch.
