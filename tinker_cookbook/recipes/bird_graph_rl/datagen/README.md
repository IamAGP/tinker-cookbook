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

## Amendment D checkpoint: step 1 complete

{
  "current_written_training_questions": 600,
  "current_mix": {
    "aggregation": {
      "none": {
        "count": 190,
        "achieved_percent": 31.666666666666668,
        "target_percent": 55,
        "delta_points": -23.333333333333332
      },
      "count": {
        "count": 31,
        "achieved_percent": 5.166666666666667,
        "target_percent": 25,
        "delta_points": -19.833333333333332
      },
      "sum": {
        "count": 119,
        "achieved_percent": 19.833333333333332,
        "target_percent": 7,
        "delta_points": 12.833333333333332
      },
      "count distinct": {
        "count": 74,
        "achieved_percent": 12.333333333333334,
        "target_percent": 3,
        "delta_points": 9.333333333333334
      },
      "avg": {
        "count": 95,
        "achieved_percent": 15.833333333333334,
        "target_percent": 3,
        "delta_points": 12.833333333333334
      },
      "max": {
        "count": 46,
        "achieved_percent": 7.666666666666667,
        "target_percent": 2,
        "delta_points": 5.666666666666667
      },
      "min": {
        "count": 32,
        "achieved_percent": 5.333333333333333,
        "target_percent": 1,
        "delta_points": 4.333333333333333
      },
      "more than one aggregate": {
        "count": 13,
        "achieved_percent": 2.1666666666666665,
        "target_percent": 5,
        "delta_points": -2.8333333333333335
      }
    },
    "ordering": {
      "none": {
        "count": 377,
        "achieved_percent": 62.833333333333336,
        "target_percent": 83,
        "delta_points": -20.166666666666664
      },
      "top 1": {
        "count": 84,
        "achieved_percent": 14.0,
        "target_percent": 14,
        "delta_points": 0.0
      },
      "top-k": {
        "count": 38,
        "achieved_percent": 6.333333333333333,
        "target_percent": 1,
        "delta_points": 5.333333333333333
      },
      "n-th ranked": {
        "count": 9,
        "achieved_percent": 1.5,
        "target_percent": 0,
        "delta_points": 1.5
      },
      "order with no limit": {
        "count": 92,
        "achieved_percent": 15.333333333333334,
        "target_percent": 0,
        "delta_points": 15.333333333333334
      }
    },
    "grouping": {
      "yes": {
        "count": 33,
        "achieved_percent": 5.5,
        "target_percent": 10,
        "delta_points": -4.5
      }
    },
    "extras": {
      "none": {
        "count": 449,
        "achieved_percent": 74.83333333333333,
        "target_percent": 72,
        "delta_points": 2.8333333333333286
      },
      "distinct projection": {
        "count": 31,
        "achieved_percent": 5.166666666666667,
        "target_percent": 9,
        "delta_points": -3.833333333333333
      },
      "ratio": {
        "count": 13,
        "achieved_percent": 2.1666666666666665,
        "target_percent": 8,
        "delta_points": -5.833333333333334
      },
      "conditional aggregate": {
        "count": 65,
        "achieved_percent": 10.833333333333334,
        "target_percent": 8,
        "delta_points": 2.833333333333334
      },
      "negation": {
        "count": 0,
        "achieved_percent": 0.0,
        "target_percent": 3,
        "delta_points": -3.0
      },
      "comparison of two named entities": {
        "count": 18,
        "achieved_percent": 3.0,
        "target_percent": 2,
        "delta_points": 1.0
      },
      "having": {
        "count": 19,
        "achieved_percent": 3.1666666666666665,
        "target_percent": 1,
        "delta_points": 2.1666666666666665
      },
      "existence": {
        "count": 5,
        "achieved_percent": 0.8333333333333334,
        "target_percent": 1,
        "delta_points": -0.16666666666666663
      }
    },
    "columns": {
      "one": {
        "count": 408,
        "achieved_percent": 68.0,
        "target_percent": 84,
        "delta_points": -16.0
      },
      "two": {
        "count": 192,
        "achieved_percent": 32.0,
        "target_percent": 12,
        "delta_points": 20.0
      },
      "three or more": {
        "count": 0,
        "achieved_percent": 0.0,
        "target_percent": 4,
        "delta_points": -4.0
      }
    },
    "depth": {
      "0-1": {
        "count": 296,
        "achieved_percent": 49.333333333333336,
        "target_percent": 70,
        "delta_points": -20.666666666666664
      },
      "2": {
        "count": 209,
        "achieved_percent": 34.833333333333336,
        "target_percent": 20,
        "delta_points": 14.833333333333336
      },
      "3-4": {
        "count": 95,
        "achieved_percent": 15.833333333333334,
        "target_percent": 10,
        "delta_points": 5.833333333333334
      }
    }
  },
  "available_training_instances": 1331,
  "held_component_count": 28,
  "decisions": [
    "Add unordered single-column lookups, unordered distinct projections, plain entity counts and grouped authored-post counts; render ranking answers as a single meaningful column where needed.",
    "Count means COUNT of entities without DISTINCT; reject samples where matching multiplicity would change the count. Existing explicit distinct-count families retain their classification.",
    "Ratios use SUM and COUNT and are classified as more than one aggregate; conditional SUM(CASE ... THEN 1 ...) is classified by its intended count meaning, consistent with the frozen signature.",
    "Return width is not part of the existing signature tuple, so meaningful projection changes may reuse a training structure signature with new v4 instance ids.",
    "Negation is explicitly entirely held out and cannot be introduced; its achieved share must be zero.",
    "Targets are approximate marginals, not an exclusive partition: their stated aggregation percentages do not sum to exactly a whole, and extras can overlap. Ordering under-one-percent / at-most-one-percent are enforced as upper bounds, not exact zero targets."
  ],
  "aggregation_target_sum": 101,
  "extras_target_sum": 104
}

Next: execute candidate additions. Existing outputs are frozen; all new outputs are confined to out/v4.

## Amendment D checkpoint: step 2 complete

{
  "candidate_structures": 170,
  "new_instances_accepted": 1713,
  "new_signatures_accepted": 125,
  "rejections": {
    "trivial_constant_answer": 183,
    "fewer_than_6": 4,
    "row_count": 280,
    "multiplicity": 64,
    "all_null": 14,
    "cut_boundary_tie": 91
  }
}

All new instances were executed twice and matched. Count candidates additionally checked COUNT equals COUNT DISTINCT to reject multiplicity. Next: select the fixed-size mix.

## Amendment D checkpoint: step 2 complete

{
  "candidate_structures": 214,
  "new_instances_accepted": 1981,
  "new_signatures_accepted": 149,
  "rejections": {
    "all_null_extra_column": 173,
    "trivial_constant_answer": 186,
    "fewer_than_6": 33,
    "row_count": 639,
    "multiplicity": 173,
    "all_null": 10,
    "cut_boundary_tie": 91
  }
}

All new instances were executed twice and matched. Count candidates additionally checked COUNT equals COUNT DISTINCT to reject multiplicity. Next: select the fixed-size mix.

## Amendment D checkpoint: step 3 complete

{
  "status": "step 3 complete; individual wording pending",
  "selected_instances": 320,
  "questions_written": 0,
  "mix": {
    "aggregation": {
      "none": {
        "count": 176,
        "achieved_percent": 55.0,
        "target_percent": 55,
        "delta_points": 0.0,
        "within_tolerance": true
      },
      "count": {
        "count": 80,
        "achieved_percent": 25.0,
        "target_percent": 25,
        "delta_points": 0.0,
        "within_tolerance": true
      },
      "sum": {
        "count": 19,
        "achieved_percent": 5.9375,
        "target_percent": 7,
        "delta_points": -1.0625,
        "within_tolerance": true
      },
      "count distinct": {
        "count": 9,
        "achieved_percent": 2.8125,
        "target_percent": 3,
        "delta_points": -0.1875,
        "within_tolerance": true
      },
      "avg": {
        "count": 5,
        "achieved_percent": 1.5625,
        "target_percent": 3,
        "delta_points": -1.4375,
        "within_tolerance": true
      },
      "max": {
        "count": 4,
        "achieved_percent": 1.25,
        "target_percent": 2,
        "delta_points": -0.75,
        "within_tolerance": true
      },
      "min": {
        "count": 3,
        "achieved_percent": 0.9375,
        "target_percent": 1,
        "delta_points": -0.0625,
        "within_tolerance": true
      },
      "more than one aggregate": {
        "count": 24,
        "achieved_percent": 7.5,
        "target_percent": 5,
        "delta_points": 2.5,
        "within_tolerance": true
      }
    },
    "ordering": {
      "none": {
        "count": 266,
        "achieved_percent": 83.125,
        "target_percent": 83,
        "delta_points": 0.125,
        "within_tolerance": true
      },
      "top 1": {
        "count": 45,
        "achieved_percent": 14.0625,
        "target_percent": 14,
        "delta_points": 0.0625,
        "within_tolerance": true
      },
      "top-k": {
        "count": 4,
        "achieved_percent": 1.25,
        "target_percent": 1,
        "delta_points": 0.25,
        "within_tolerance": true
      },
      "n-th ranked": {
        "count": 1,
        "achieved_percent": 0.3125,
        "target_percent": 0,
        "delta_points": 0.3125,
        "within_tolerance": true
      },
      "order with no limit": {
        "count": 4,
        "achieved_percent": 1.25,
        "target_percent": 0,
        "delta_points": 1.25,
        "within_tolerance": false
      }
    },
    "grouping": {
      "yes": {
        "count": 32,
        "achieved_percent": 10.0,
        "target_percent": 10,
        "delta_points": 0.0,
        "within_tolerance": true
      }
    },
    "extras": {
      "none": {
        "count": 230,
        "achieved_percent": 71.875,
        "target_percent": 72,
        "delta_points": -0.125,
        "within_tolerance": true
      },
      "distinct projection": {
        "count": 29,
        "achieved_percent": 9.0625,
        "target_percent": 9,
        "delta_points": 0.0625,
        "within_tolerance": true
      },
      "ratio": {
        "count": 24,
        "achieved_percent": 7.5,
        "target_percent": 8,
        "delta_points": -0.5,
        "within_tolerance": true
      },
      "conditional aggregate": {
        "count": 26,
        "achieved_percent": 8.125,
        "target_percent": 8,
        "delta_points": 0.125,
        "within_tolerance": true
      },
      "negation": {
        "count": 0,
        "achieved_percent": 0.0,
        "target_percent": 3,
        "delta_points": -3.0,
        "within_tolerance": true
      },
      "comparison of two named entities": {
        "count": 6,
        "achieved_percent": 1.875,
        "target_percent": 2,
        "delta_points": -0.125,
        "within_tolerance": true
      },
      "having": {
        "count": 3,
        "achieved_percent": 0.9375,
        "target_percent": 1,
        "delta_points": -0.0625,
        "within_tolerance": true
      },
      "existence": {
        "count": 2,
        "achieved_percent": 0.625,
        "target_percent": 1,
        "delta_points": -0.375,
        "within_tolerance": true
      }
    },
    "columns": {
      "one": {
        "count": 269,
        "achieved_percent": 84.0625,
        "target_percent": 84,
        "delta_points": 0.0625,
        "within_tolerance": true
      },
      "two": {
        "count": 38,
        "achieved_percent": 11.875,
        "target_percent": 12,
        "delta_points": -0.125,
        "within_tolerance": true
      },
      "three or more": {
        "count": 13,
        "achieved_percent": 4.0625,
        "target_percent": 4,
        "delta_points": 0.0625,
        "within_tolerance": true
      }
    },
    "depth": {
      "0-1": {
        "count": 224,
        "achieved_percent": 70.0,
        "target_percent": 70,
        "delta_points": 0.0,
        "within_tolerance": true
      },
      "2": {
        "count": 64,
        "achieved_percent": 20.0,
        "target_percent": 20,
        "delta_points": 0.0,
        "within_tolerance": true
      },
      "3-4": {
        "count": 32,
        "achieved_percent": 10.0,
        "target_percent": 10,
        "delta_points": 0.0,
        "within_tolerance": true
      }
    }
  },
  "structure_counts": {
    "reused": 55,
    "new": 99
  },
  "instance_counts": {
    "reused": 91,
    "new": 229
  },
  "max_questions_per_structure_planned": 5,
  "heldout_checks": {
    "no_heldout_signature": true,
    "no_heldout_component_introduced": true,
    "signature_collisions": [],
    "introduced_components": []
  },
  "frozen_files_unchanged": true,
  "hints": {
    "with_hint": 296,
    "share": 0.925
  },
  "interpretations": [
    "Add unordered single-column lookups, unordered distinct projections, plain entity counts and grouped authored-post counts; render ranking answers as a single meaningful column where needed.",
    "Count means COUNT of entities without DISTINCT; reject samples where matching multiplicity would change the count. Existing explicit distinct-count families retain their classification.",
    "Ratios use SUM and COUNT and are classified as more than one aggregate; conditional SUM(CASE ... THEN 1 ...) is classified by its intended count meaning, consistent with the frozen signature.",
    "Return width is not part of the existing signature tuple, so meaningful projection changes may reuse a training structure signature with new v4 instance ids.",
    "Negation is explicitly entirely held out and cannot be introduced; its achieved share must be zero.",
    "Targets are approximate marginals, not an exclusive partition: their stated aggregation percentages do not sum to exactly a whole, and extras can overlap. Ordering under-one-percent / at-most-one-percent are enforced as upper bounds, not exact zero targets."
  ]
}

Next: write each selected question individually; no v4 questions are yet ready for training.

## Amendment D checkpoint: step 3 complete

{
  "status": "step 3 complete; individual wording pending",
  "selected_instances": 320,
  "questions_written": 0,
  "how_many_combined": {
    "count": 89,
    "achieved_percent": 27.8125,
    "target_percent": 28
  },
  "distinct_projection_ceiling_pass": true,
  "depth_departure": "The deeper-hop target is deliberately above the human distribution, as stated in amendment D notes.",
  "mix": {
    "aggregation": {
      "none": {
        "count": 176,
        "achieved_percent": 55.0,
        "target_percent": 55,
        "delta_points": 0.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "count": {
        "count": 80,
        "achieved_percent": 25.0,
        "target_percent": 25,
        "delta_points": 0.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "sum": {
        "count": 19,
        "achieved_percent": 5.9375,
        "target_percent": 7,
        "delta_points": -1.0625,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "count distinct": {
        "count": 9,
        "achieved_percent": 2.8125,
        "target_percent": 3,
        "delta_points": -0.1875,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "avg": {
        "count": 5,
        "achieved_percent": 1.5625,
        "target_percent": 3,
        "delta_points": -1.4375,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "max": {
        "count": 4,
        "achieved_percent": 1.25,
        "target_percent": 2,
        "delta_points": -0.75,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "min": {
        "count": 3,
        "achieved_percent": 0.9375,
        "target_percent": 1,
        "delta_points": -0.0625,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "more than one aggregate": {
        "count": 24,
        "achieved_percent": 7.5,
        "target_percent": 5,
        "delta_points": 2.5,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      }
    },
    "ordering": {
      "none": {
        "count": 266,
        "achieved_percent": 83.125,
        "target_percent": 83,
        "delta_points": 0.125,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "top 1": {
        "count": 45,
        "achieved_percent": 14.0625,
        "target_percent": 14,
        "delta_points": 0.0625,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "top-k": {
        "count": 3,
        "achieved_percent": 0.9375,
        "target_percent": 1,
        "delta_points": -0.0625,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "n-th ranked": {
        "count": 3,
        "achieved_percent": 0.9375,
        "target_percent": 0,
        "delta_points": 0.9375,
        "target_rule": "<1%",
        "within_tolerance": true
      },
      "order with no limit": {
        "count": 3,
        "achieved_percent": 0.9375,
        "target_percent": 0,
        "delta_points": 0.9375,
        "target_rule": "<=1%",
        "within_tolerance": true
      }
    },
    "grouping": {
      "yes": {
        "count": 32,
        "achieved_percent": 10.0,
        "target_percent": 10,
        "delta_points": 0.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      }
    },
    "extras": {
      "none": {
        "count": 231,
        "achieved_percent": 72.1875,
        "target_percent": 72,
        "delta_points": 0.1875,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "distinct projection": {
        "count": 28,
        "achieved_percent": 8.75,
        "target_percent": 9,
        "delta_points": -0.25,
        "target_rule": "<=9%",
        "within_tolerance": true
      },
      "ratio": {
        "count": 24,
        "achieved_percent": 7.5,
        "target_percent": 8,
        "delta_points": -0.5,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "conditional aggregate": {
        "count": 26,
        "achieved_percent": 8.125,
        "target_percent": 8,
        "delta_points": 0.125,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "negation": {
        "count": 0,
        "achieved_percent": 0.0,
        "target_percent": 3,
        "delta_points": -3.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "comparison of two named entities": {
        "count": 7,
        "achieved_percent": 2.1875,
        "target_percent": 2,
        "delta_points": 0.1875,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "having": {
        "count": 2,
        "achieved_percent": 0.625,
        "target_percent": 1,
        "delta_points": -0.375,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "existence": {
        "count": 2,
        "achieved_percent": 0.625,
        "target_percent": 1,
        "delta_points": -0.375,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      }
    },
    "columns": {
      "one": {
        "count": 269,
        "achieved_percent": 84.0625,
        "target_percent": 84,
        "delta_points": 0.0625,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "two": {
        "count": 38,
        "achieved_percent": 11.875,
        "target_percent": 12,
        "delta_points": -0.125,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "three or more": {
        "count": 13,
        "achieved_percent": 4.0625,
        "target_percent": 4,
        "delta_points": 0.0625,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      }
    },
    "depth": {
      "0-1": {
        "count": 224,
        "achieved_percent": 70.0,
        "target_percent": 70,
        "delta_points": 0.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "2": {
        "count": 64,
        "achieved_percent": 20.0,
        "target_percent": 20,
        "delta_points": 0.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "3-4": {
        "count": 32,
        "achieved_percent": 10.0,
        "target_percent": 10,
        "delta_points": 0.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      }
    }
  },
  "structure_counts": {
    "reused": 56,
    "new": 101
  },
  "instance_counts": {
    "reused": 90,
    "new": 230
  },
  "max_questions_per_structure_planned": 5,
  "heldout_checks": {
    "no_heldout_signature": true,
    "no_heldout_component_introduced": true,
    "signature_collisions": [],
    "introduced_components": []
  },
  "frozen_files_unchanged": true,
  "hints": {
    "with_hint": 291,
    "share": 0.909375
  },
  "interpretations": [
    "Add unordered single-column lookups, unordered distinct projections, plain entity counts and grouped authored-post counts; render ranking answers as a single meaningful column where needed.",
    "Count means COUNT of entities without DISTINCT; reject samples where matching multiplicity would change the count. Existing explicit distinct-count families retain their classification.",
    "Ratios use SUM and COUNT and are classified as more than one aggregate; conditional SUM(CASE ... THEN 1 ...) is classified by its intended count meaning, consistent with the frozen signature.",
    "Return width is not part of the existing signature tuple, so meaningful projection changes may reuse a training structure signature with new v4 instance ids.",
    "Negation is explicitly entirely held out and cannot be introduced; its achieved share must be zero.",
    "Targets are approximate marginals, not an exclusive partition: their stated aggregation percentages do not sum to exactly a whole, and extras can overlap. Ordering under-one-percent / at-most-one-percent are enforced as upper bounds, not exact zero targets."
  ]
}

Next: write each selected question individually; no v4 questions are yet ready for training.

## Amendment D checkpoint: step 3 verification complete

{
  "executed": 320,
  "matched": 320,
  "rejections": {},
  "mismatched_ids": [],
  "max_runtime_ms": 335.44674993027
}

Selected-instance mix is in out/v4/report.json. Individual question writing remains pending; v4 is not ready for training. Frozen files still match the pre-run SHA-256 manifest. Test results: {"passed": 25, "command": "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tinker_cookbook/recipes/bird_graph_rl/datagen"}.

## Amendment D checkpoint: step 3 complete

{
  "status": "step 3 complete; individual wording pending",
  "selected_instances": 320,
  "questions_written": 0,
  "how_many_combined": {
    "count": 89,
    "achieved_percent": 27.8125,
    "target_percent": 28
  },
  "distinct_projection_ceiling_pass": true,
  "depth_departure": "The deeper-hop target is deliberately above the human distribution, as stated in amendment D notes.",
  "mix": {
    "aggregation": {
      "none": {
        "count": 176,
        "achieved_percent": 55.0,
        "target_percent": 55,
        "delta_points": 0.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "count": {
        "count": 80,
        "achieved_percent": 25.0,
        "target_percent": 25,
        "delta_points": 0.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "sum": {
        "count": 19,
        "achieved_percent": 5.9375,
        "target_percent": 7,
        "delta_points": -1.0625,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "count distinct": {
        "count": 9,
        "achieved_percent": 2.8125,
        "target_percent": 3,
        "delta_points": -0.1875,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "avg": {
        "count": 5,
        "achieved_percent": 1.5625,
        "target_percent": 3,
        "delta_points": -1.4375,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "max": {
        "count": 4,
        "achieved_percent": 1.25,
        "target_percent": 2,
        "delta_points": -0.75,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "min": {
        "count": 3,
        "achieved_percent": 0.9375,
        "target_percent": 1,
        "delta_points": -0.0625,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "more than one aggregate": {
        "count": 24,
        "achieved_percent": 7.5,
        "target_percent": 5,
        "delta_points": 2.5,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      }
    },
    "ordering": {
      "none": {
        "count": 266,
        "achieved_percent": 83.125,
        "target_percent": 83,
        "delta_points": 0.125,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "top 1": {
        "count": 45,
        "achieved_percent": 14.0625,
        "target_percent": 14,
        "delta_points": 0.0625,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "top-k": {
        "count": 3,
        "achieved_percent": 0.9375,
        "target_percent": 1,
        "delta_points": -0.0625,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "n-th ranked": {
        "count": 3,
        "achieved_percent": 0.9375,
        "target_percent": 0,
        "delta_points": 0.9375,
        "target_rule": "<1%",
        "within_tolerance": true
      },
      "order with no limit": {
        "count": 3,
        "achieved_percent": 0.9375,
        "target_percent": 0,
        "delta_points": 0.9375,
        "target_rule": "<=1%",
        "within_tolerance": true
      }
    },
    "grouping": {
      "yes": {
        "count": 32,
        "achieved_percent": 10.0,
        "target_percent": 10,
        "delta_points": 0.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      }
    },
    "extras": {
      "none": {
        "count": 231,
        "achieved_percent": 72.1875,
        "target_percent": 72,
        "delta_points": 0.1875,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "distinct projection": {
        "count": 28,
        "achieved_percent": 8.75,
        "target_percent": 9,
        "delta_points": -0.25,
        "target_rule": "<=9%",
        "within_tolerance": true
      },
      "ratio": {
        "count": 24,
        "achieved_percent": 7.5,
        "target_percent": 8,
        "delta_points": -0.5,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "conditional aggregate": {
        "count": 26,
        "achieved_percent": 8.125,
        "target_percent": 8,
        "delta_points": 0.125,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "negation": {
        "count": 0,
        "achieved_percent": 0.0,
        "target_percent": 3,
        "delta_points": -3.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "comparison of two named entities": {
        "count": 7,
        "achieved_percent": 2.1875,
        "target_percent": 2,
        "delta_points": 0.1875,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "having": {
        "count": 2,
        "achieved_percent": 0.625,
        "target_percent": 1,
        "delta_points": -0.375,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "existence": {
        "count": 2,
        "achieved_percent": 0.625,
        "target_percent": 1,
        "delta_points": -0.375,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      }
    },
    "columns": {
      "one": {
        "count": 269,
        "achieved_percent": 84.0625,
        "target_percent": 84,
        "delta_points": 0.0625,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "two": {
        "count": 38,
        "achieved_percent": 11.875,
        "target_percent": 12,
        "delta_points": -0.125,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "three or more": {
        "count": 13,
        "achieved_percent": 4.0625,
        "target_percent": 4,
        "delta_points": 0.0625,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      }
    },
    "depth": {
      "0-1": {
        "count": 224,
        "achieved_percent": 70.0,
        "target_percent": 70,
        "delta_points": 0.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "2": {
        "count": 64,
        "achieved_percent": 20.0,
        "target_percent": 20,
        "delta_points": 0.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      },
      "3-4": {
        "count": 32,
        "achieved_percent": 10.0,
        "target_percent": 10,
        "delta_points": 0.0,
        "target_rule": "about target, within three percentage points",
        "within_tolerance": true
      }
    }
  },
  "structure_counts": {
    "reused": 56,
    "new": 101
  },
  "instance_counts": {
    "reused": 90,
    "new": 230
  },
  "max_questions_per_structure_planned": 5,
  "heldout_checks": {
    "no_heldout_signature": true,
    "no_heldout_component_introduced": true,
    "signature_collisions": [],
    "introduced_components": []
  },
  "frozen_files_unchanged": true,
  "hints": {
    "with_hint": 291,
    "share": 0.909375
  },
  "interpretations": [
    "Add unordered single-column lookups, unordered distinct projections, plain entity counts and grouped authored-post counts; render ranking answers as a single meaningful column where needed.",
    "Count means COUNT of entities without DISTINCT; reject samples where matching multiplicity would change the count. Existing explicit distinct-count families retain their classification.",
    "Ratios use SUM and COUNT and are classified as more than one aggregate; conditional SUM(CASE ... THEN 1 ...) is classified by its intended count meaning, consistent with the frozen signature.",
    "Return width is not part of the existing signature tuple, so meaningful projection changes may reuse a training structure signature with new v4 instance ids.",
    "Negation is explicitly entirely held out and cannot be introduced; its achieved share must be zero.",
    "Targets are approximate marginals, not an exclusive partition: their stated aggregation percentages do not sum to exactly a whole, and extras can overlap. Ordering under-one-percent / at-most-one-percent are enforced as upper bounds, not exact zero targets."
  ]
}

Next: write each selected question individually; no v4 questions are yet ready for training.

## Amendment D checkpoint: step 3 verification complete

{
  "executed": 320,
  "matched": 320,
  "rejections": {},
  "mismatched_ids": [],
  "max_runtime_ms": 126.08433398418128
}

Selected-instance mix is in out/v4/report.json. Individual question writing remains pending; v4 is not ready for training. Frozen files still match the pre-run SHA-256 manifest. Test results: {"passed": 25, "command": "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tinker_cookbook/recipes/bird_graph_rl/datagen"}.

## Amendment D final turn checkpoint

# Amendment D selected-instance checkpoint

Status: steps 1-3 complete and verified; stopped before step 4; individual question writing pending. Selected instances are not yet a question dataset.

| Dimension | Feature | Achieved % | Target % / rule |
|---|---|---:|---|
| aggregation | none | 55.0000 | 55 |
| aggregation | count | 25.0000 | 25 |
| aggregation | sum | 5.9375 | 7 |
| aggregation | count distinct | 2.8125 | 3 |
| aggregation | avg | 1.5625 | 3 |
| aggregation | max | 1.2500 | 2 |
| aggregation | min | 0.9375 | 1 |
| aggregation | more than one aggregate | 7.5000 | 5 |
| ordering | none | 83.1250 | 83 |
| ordering | top 1 | 14.0625 | 14 |
| ordering | top-k | 0.9375 | 1 |
| ordering | n-th ranked | 0.9375 | <1 |
| ordering | order with no limit | 0.9375 | <=1 |
| grouping | yes | 10.0000 | 10 |
| extras | none | 72.1875 | 72 |
| extras | distinct projection | 8.7500 | <=9 |
| extras | ratio | 7.5000 | 8 |
| extras | conditional aggregate | 8.1250 | 8 |
| extras | negation | 0.0000 | dropped (held out) |
| extras | comparison of two named entities | 2.1875 | 2 |
| extras | having | 0.6250 | 1 |
| extras | existence | 0.6250 | 1 |
| columns | one | 84.0625 | 84 |
| columns | two | 11.8750 | 12 |
| columns | three or more | 4.0625 | 4 |
| depth | 0-1 | 70.0000 | 70 |
| depth | 2 | 20.0000 | 20 |
| depth | 3-4 | 10.0000 | 10 |

Combined how-many share: 27.8125% against 28%.

Structures: {'reused': 56, 'new': 101}. Instances: {'reused': 90, 'new': 230}. Questions written: 0. Hints: {'with_hint': 291, 'share': 0.909375}. Maximum selected instances per structure: 5.

Held-out checks: {"no_heldout_signature": true, "no_heldout_component_introduced": true, "signature_collisions": [], "introduced_components": []}. Frozen-file hash matches: 29. Independent live replay: {"executed": 320, "matched": 320, "rejections": {}, "mismatched_ids": [], "max_runtime_ms": 126.08433398418128}. Unit tests: {"passed": 25, "command": "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tinker_cookbook/recipes/bird_graph_rl/datagen", "failures": 0, "errors": 0}.

An initial candidate for an extra Tag property produced unknown-property warnings on the live graph. Removed Tag third-column candidates, rejected all-null extra columns, rebuilt the v4 pool, and verified the final selection independently. All warnings remain in debug.log; no frozen artifacts changed.

This turn prepares Amendment D first batch only. Amendment D2 is present in SPEC.md but the first batch is not delivered yet; no second batch was started.

Write the selected questions individually into questions_v4_train.jsonl in checkpointed batches. Then compute held-out question overlap and mark the deliverable complete. Do not regenerate or reselect the verified instances.

## Individually authored v4 question batch

{
  "batch_start": 0,
  "batch_written": 100,
  "questions_written": 100,
  "selected_instances": 320,
  "selected_instance_sha256": "90aabd4910a78b558329cae81beeb67fae952b07a189033771042f01aaddb70d",
  "next_queue_index": 100
}

Continue with the frozen authoring queue. Instances and hints remain unchanged.

## Individually authored v4 question batch

{
  "batch_start": 100,
  "batch_written": 100,
  "questions_written": 200,
  "selected_instances": 320,
  "selected_instance_sha256": "90aabd4910a78b558329cae81beeb67fae952b07a189033771042f01aaddb70d",
  "next_queue_index": 200
}

Continue with the frozen authoring queue. Instances and hints remain unchanged.

## Individually authored v4 question batch

{
  "batch_start": 200,
  "batch_written": 100,
  "questions_written": 300,
  "selected_instances": 320,
  "selected_instance_sha256": "90aabd4910a78b558329cae81beeb67fae952b07a189033771042f01aaddb70d",
  "next_queue_index": 300
}

Continue with the frozen authoring queue. Instances and hints remain unchanged.

## Individually authored v4 question batch

{
  "batch_start": 300,
  "batch_written": 20,
  "questions_written": 320,
  "selected_instances": 320,
  "selected_instance_sha256": "90aabd4910a78b558329cae81beeb67fae952b07a189033771042f01aaddb70d",
  "next_queue_index": 320
}

Continue with the frozen authoring queue. Instances and hints remain unchanged.

## First v4 question set complete

{
  "selected_instances": 320,
  "questions_written": 320,
  "unique_instance_ids": 320,
  "complete_coverage": true,
  "heldout_questions_checked": 624,
  "heldout_exact_overlaps": [],
  "heldout_normalized_overlaps": [],
  "duplicate_questions": 0,
  "alias_mentions": [],
  "prohibited_vocabulary": [],
  "identical_subject_normalized_frames_within_structure": [],
  "max_questions_per_structure": 5,
  "selected_instances_unchanged": true
}

Questions were individually composed in the numbered v4 batch modules and polished after reading the rendered text. Literal and subject helpers bind data; no question-generation templates were used. Hints and selected instances were not changed. Frame checks are a mechanical screen, not an independent human naturalness review.

## Second batch selection checkpoint

{
  "status": "selected; verifying against live graph",
  "selected_instances": 280,
  "questions_written": 0,
  "mix": {
    "aggregation": {
      "none": {
        "count": 154,
        "achieved_percent": 55.0,
        "target_percent": 55
      },
      "count": {
        "count": 70,
        "achieved_percent": 25.0,
        "target_percent": 25
      },
      "sum": {
        "count": 17,
        "achieved_percent": 6.071428571428571,
        "target_percent": 7
      },
      "count distinct": {
        "count": 8,
        "achieved_percent": 2.857142857142857,
        "target_percent": 3
      },
      "avg": {
        "count": 4,
        "achieved_percent": 1.4285714285714286,
        "target_percent": 3
      },
      "max": {
        "count": 3,
        "achieved_percent": 1.0714285714285714,
        "target_percent": 2
      },
      "min": {
        "count": 3,
        "achieved_percent": 1.0714285714285714,
        "target_percent": 1
      },
      "more than one aggregate": {
        "count": 21,
        "achieved_percent": 7.5,
        "target_percent": 5
      }
    },
    "ordering": {
      "none": {
        "count": 233,
        "achieved_percent": 83.21428571428571,
        "target_percent": 83
      },
      "top 1": {
        "count": 39,
        "achieved_percent": 13.928571428571429,
        "target_percent": 14
      },
      "top-k": {
        "count": 4,
        "achieved_percent": 1.4285714285714286,
        "target_percent": 1
      },
      "n-th ranked": {
        "count": 2,
        "achieved_percent": 0.7142857142857143,
        "target_percent": 0
      },
      "order with no limit": {
        "count": 2,
        "achieved_percent": 0.7142857142857143,
        "target_percent": 0
      }
    },
    "grouping": {
      "yes": {
        "count": 17,
        "achieved_percent": 6.071428571428571,
        "target_percent": 10
      }
    },
    "extras": {
      "none": {
        "count": 202,
        "achieved_percent": 72.14285714285714,
        "target_percent": 72
      },
      "distinct projection": {
        "count": 25,
        "achieved_percent": 8.928571428571429,
        "target_percent": 9
      },
      "ratio": {
        "count": 21,
        "achieved_percent": 7.5,
        "target_percent": 8
      },
      "conditional aggregate": {
        "count": 22,
        "achieved_percent": 7.857142857142857,
        "target_percent": 8
      },
      "negation": {
        "count": 0,
        "achieved_percent": 0.0,
        "target_percent": 3
      },
      "comparison of two named entities": {
        "count": 5,
        "achieved_percent": 1.7857142857142858,
        "target_percent": 2
      },
      "having": {
        "count": 2,
        "achieved_percent": 0.7142857142857143,
        "target_percent": 1
      },
      "existence": {
        "count": 3,
        "achieved_percent": 1.0714285714285714,
        "target_percent": 1
      }
    },
    "columns": {
      "one": {
        "count": 235,
        "achieved_percent": 83.92857142857143,
        "target_percent": 84
      },
      "two": {
        "count": 34,
        "achieved_percent": 12.142857142857142,
        "target_percent": 12
      },
      "three or more": {
        "count": 11,
        "achieved_percent": 3.9285714285714284,
        "target_percent": 4
      }
    },
    "depth": {
      "0-1": {
        "count": 196,
        "achieved_percent": 70.0,
        "target_percent": 70
      },
      "2": {
        "count": 56,
        "achieved_percent": 20.0,
        "target_percent": 20
      },
      "3-4": {
        "count": 28,
        "achieved_percent": 10.0,
        "target_percent": 10
      }
    }
  },
  "structure_counts": {
    "reused": 43,
    "new": 98
  },
  "checks": {
    "disjoint_instance_ids": true,
    "disjoint_query_parameter_pairs": true,
    "combined_max_per_structure": 5,
    "no_heldout_signature": true,
    "no_heldout_component_introduced": true
  },
  "hints": {
    "with_hint": 254,
    "share": 0.9071428571428571
  },
  "first_batch_hashes": {
    "instances_v4_train.jsonl": "90aabd4910a78b558329cae81beeb67fae952b07a189033771042f01aaddb70d",
    "structures_v4_train.jsonl": "e517ff3ed01af1a010d52085bc84bf70c87e1d7fee08c1f0be9ff5985d2f0379",
    "questions_v4_train.jsonl": "9427dab24e1274840ab86a056f26b0f6929e6344b067901f56247976e3031b56",
    "new_structures.json": "780a390ea580032fad94ff203e6303267996bbf3f9217dfa91e7caee30fa2f2c"
  },
  "declared_shortfalls": [
    "Negation is held out entirely and omitted."
  ],
  "spec_arithmetic_note": {
    "first_requested": 320,
    "second_requested": 280,
    "combined_requested": 600,
    "stated_total_in_D2": 592,
    "interpretation": "Follow the explicit batch sizes; the stated total differs from their sum."
  }
}

## Second batch verification checkpoint

{
  "status": "selected and live-verified; individual question wording pending",
  "selected_instances": 280,
  "questions_written": 0,
  "mix": {
    "aggregation": {
      "none": {
        "count": 154,
        "achieved_percent": 55.0,
        "target_percent": 55
      },
      "count": {
        "count": 70,
        "achieved_percent": 25.0,
        "target_percent": 25
      },
      "sum": {
        "count": 17,
        "achieved_percent": 6.071428571428571,
        "target_percent": 7
      },
      "count distinct": {
        "count": 8,
        "achieved_percent": 2.857142857142857,
        "target_percent": 3
      },
      "avg": {
        "count": 4,
        "achieved_percent": 1.4285714285714286,
        "target_percent": 3
      },
      "max": {
        "count": 3,
        "achieved_percent": 1.0714285714285714,
        "target_percent": 2
      },
      "min": {
        "count": 3,
        "achieved_percent": 1.0714285714285714,
        "target_percent": 1
      },
      "more than one aggregate": {
        "count": 21,
        "achieved_percent": 7.5,
        "target_percent": 5
      }
    },
    "ordering": {
      "none": {
        "count": 233,
        "achieved_percent": 83.21428571428571,
        "target_percent": 83
      },
      "top 1": {
        "count": 39,
        "achieved_percent": 13.928571428571429,
        "target_percent": 14
      },
      "top-k": {
        "count": 4,
        "achieved_percent": 1.4285714285714286,
        "target_percent": 1
      },
      "n-th ranked": {
        "count": 2,
        "achieved_percent": 0.7142857142857143,
        "target_percent": 0
      },
      "order with no limit": {
        "count": 2,
        "achieved_percent": 0.7142857142857143,
        "target_percent": 0
      }
    },
    "grouping": {
      "yes": {
        "count": 17,
        "achieved_percent": 6.071428571428571,
        "target_percent": 10
      }
    },
    "extras": {
      "none": {
        "count": 202,
        "achieved_percent": 72.14285714285714,
        "target_percent": 72
      },
      "distinct projection": {
        "count": 25,
        "achieved_percent": 8.928571428571429,
        "target_percent": 9
      },
      "ratio": {
        "count": 21,
        "achieved_percent": 7.5,
        "target_percent": 8
      },
      "conditional aggregate": {
        "count": 22,
        "achieved_percent": 7.857142857142857,
        "target_percent": 8
      },
      "negation": {
        "count": 0,
        "achieved_percent": 0.0,
        "target_percent": 3
      },
      "comparison of two named entities": {
        "count": 5,
        "achieved_percent": 1.7857142857142858,
        "target_percent": 2
      },
      "having": {
        "count": 2,
        "achieved_percent": 0.7142857142857143,
        "target_percent": 1
      },
      "existence": {
        "count": 3,
        "achieved_percent": 1.0714285714285714,
        "target_percent": 1
      }
    },
    "columns": {
      "one": {
        "count": 235,
        "achieved_percent": 83.92857142857143,
        "target_percent": 84
      },
      "two": {
        "count": 34,
        "achieved_percent": 12.142857142857142,
        "target_percent": 12
      },
      "three or more": {
        "count": 11,
        "achieved_percent": 3.9285714285714284,
        "target_percent": 4
      }
    },
    "depth": {
      "0-1": {
        "count": 196,
        "achieved_percent": 70.0,
        "target_percent": 70
      },
      "2": {
        "count": 56,
        "achieved_percent": 20.0,
        "target_percent": 20
      },
      "3-4": {
        "count": 28,
        "achieved_percent": 10.0,
        "target_percent": 10
      }
    }
  },
  "structure_counts": {
    "reused": 43,
    "new": 98
  },
  "checks": {
    "disjoint_instance_ids": true,
    "disjoint_query_parameter_pairs": true,
    "combined_max_per_structure": 5,
    "no_heldout_signature": true,
    "no_heldout_component_introduced": true,
    "first_batch_unchanged": true
  },
  "hints": {
    "with_hint": 254,
    "share": 0.9071428571428571
  },
  "first_batch_hashes": {
    "instances_v4_train.jsonl": "90aabd4910a78b558329cae81beeb67fae952b07a189033771042f01aaddb70d",
    "structures_v4_train.jsonl": "e517ff3ed01af1a010d52085bc84bf70c87e1d7fee08c1f0be9ff5985d2f0379",
    "questions_v4_train.jsonl": "9427dab24e1274840ab86a056f26b0f6929e6344b067901f56247976e3031b56",
    "new_structures.json": "780a390ea580032fad94ff203e6303267996bbf3f9217dfa91e7caee30fa2f2c"
  },
  "declared_shortfalls": [
    "Negation is held out entirely and omitted."
  ],
  "spec_arithmetic_note": {
    "first_requested": 320,
    "second_requested": 280,
    "combined_requested": 600,
    "stated_total_in_D2": 592,
    "interpretation": "Follow the explicit batch sizes; the stated total differs from their sum."
  },
  "verification": {
    "executed": 280,
    "matched": 280,
    "stable": 280,
    "rejections": {},
    "mismatched_ids": []
  }
}

## Second batch grouping additions verified

{
  "natural_new_group_structures": 3,
  "new_verified_instances": 36,
  "rejections": {
    "row_count": 32,
    "insufficient_or_constant": 4
  }
}

## Second batch selection checkpoint

{
  "status": "selected; verifying against live graph",
  "selected_instances": 280,
  "questions_written": 0,
  "mix": {
    "aggregation": {
      "none": {
        "count": 154,
        "achieved_percent": 55.0,
        "target_percent": 55
      },
      "count": {
        "count": 70,
        "achieved_percent": 25.0,
        "target_percent": 25
      },
      "sum": {
        "count": 17,
        "achieved_percent": 6.071428571428571,
        "target_percent": 7
      },
      "count distinct": {
        "count": 8,
        "achieved_percent": 2.857142857142857,
        "target_percent": 3
      },
      "avg": {
        "count": 4,
        "achieved_percent": 1.4285714285714286,
        "target_percent": 3
      },
      "max": {
        "count": 3,
        "achieved_percent": 1.0714285714285714,
        "target_percent": 2
      },
      "min": {
        "count": 3,
        "achieved_percent": 1.0714285714285714,
        "target_percent": 1
      },
      "more than one aggregate": {
        "count": 21,
        "achieved_percent": 7.5,
        "target_percent": 5
      }
    },
    "ordering": {
      "none": {
        "count": 233,
        "achieved_percent": 83.21428571428571,
        "target_percent": 83
      },
      "top 1": {
        "count": 39,
        "achieved_percent": 13.928571428571429,
        "target_percent": 14
      },
      "top-k": {
        "count": 4,
        "achieved_percent": 1.4285714285714286,
        "target_percent": 1
      },
      "n-th ranked": {
        "count": 2,
        "achieved_percent": 0.7142857142857143,
        "target_percent": 0
      },
      "order with no limit": {
        "count": 2,
        "achieved_percent": 0.7142857142857143,
        "target_percent": 0
      }
    },
    "grouping": {
      "yes": {
        "count": 28,
        "achieved_percent": 10.0,
        "target_percent": 10
      }
    },
    "extras": {
      "none": {
        "count": 202,
        "achieved_percent": 72.14285714285714,
        "target_percent": 72
      },
      "distinct projection": {
        "count": 25,
        "achieved_percent": 8.928571428571429,
        "target_percent": 9
      },
      "ratio": {
        "count": 21,
        "achieved_percent": 7.5,
        "target_percent": 8
      },
      "conditional aggregate": {
        "count": 22,
        "achieved_percent": 7.857142857142857,
        "target_percent": 8
      },
      "negation": {
        "count": 0,
        "achieved_percent": 0.0,
        "target_percent": 3
      },
      "comparison of two named entities": {
        "count": 5,
        "achieved_percent": 1.7857142857142858,
        "target_percent": 2
      },
      "having": {
        "count": 2,
        "achieved_percent": 0.7142857142857143,
        "target_percent": 1
      },
      "existence": {
        "count": 3,
        "achieved_percent": 1.0714285714285714,
        "target_percent": 1
      }
    },
    "columns": {
      "one": {
        "count": 235,
        "achieved_percent": 83.92857142857143,
        "target_percent": 84
      },
      "two": {
        "count": 34,
        "achieved_percent": 12.142857142857142,
        "target_percent": 12
      },
      "three or more": {
        "count": 11,
        "achieved_percent": 3.9285714285714284,
        "target_percent": 4
      }
    },
    "depth": {
      "0-1": {
        "count": 196,
        "achieved_percent": 70.0,
        "target_percent": 70
      },
      "2": {
        "count": 56,
        "achieved_percent": 20.0,
        "target_percent": 20
      },
      "3-4": {
        "count": 28,
        "achieved_percent": 10.0,
        "target_percent": 10
      }
    }
  },
  "structure_counts": {
    "reused": 41,
    "new": 101
  },
  "checks": {
    "disjoint_instance_ids": true,
    "disjoint_query_parameter_pairs": true,
    "combined_max_per_structure": 5,
    "no_heldout_signature": true,
    "no_heldout_component_introduced": true
  },
  "hints": {
    "with_hint": 256,
    "share": 0.9142857142857143
  },
  "first_batch_hashes": {
    "instances_v4_train.jsonl": "90aabd4910a78b558329cae81beeb67fae952b07a189033771042f01aaddb70d",
    "structures_v4_train.jsonl": "e517ff3ed01af1a010d52085bc84bf70c87e1d7fee08c1f0be9ff5985d2f0379",
    "questions_v4_train.jsonl": "9427dab24e1274840ab86a056f26b0f6929e6344b067901f56247976e3031b56",
    "new_structures.json": "780a390ea580032fad94ff203e6303267996bbf3f9217dfa91e7caee30fa2f2c"
  },
  "declared_shortfalls": [
    "Negation is held out entirely and omitted."
  ],
  "spec_arithmetic_note": {
    "first_requested": 320,
    "second_requested": 280,
    "combined_requested": 600,
    "stated_total_in_D2": 592,
    "interpretation": "Follow the explicit batch sizes; the stated total differs from their sum."
  }
}

## Second batch verification checkpoint

{
  "status": "selected and live-verified; individual question wording pending",
  "selected_instances": 280,
  "questions_written": 0,
  "mix": {
    "aggregation": {
      "none": {
        "count": 154,
        "achieved_percent": 55.0,
        "target_percent": 55
      },
      "count": {
        "count": 70,
        "achieved_percent": 25.0,
        "target_percent": 25
      },
      "sum": {
        "count": 17,
        "achieved_percent": 6.071428571428571,
        "target_percent": 7
      },
      "count distinct": {
        "count": 8,
        "achieved_percent": 2.857142857142857,
        "target_percent": 3
      },
      "avg": {
        "count": 4,
        "achieved_percent": 1.4285714285714286,
        "target_percent": 3
      },
      "max": {
        "count": 3,
        "achieved_percent": 1.0714285714285714,
        "target_percent": 2
      },
      "min": {
        "count": 3,
        "achieved_percent": 1.0714285714285714,
        "target_percent": 1
      },
      "more than one aggregate": {
        "count": 21,
        "achieved_percent": 7.5,
        "target_percent": 5
      }
    },
    "ordering": {
      "none": {
        "count": 233,
        "achieved_percent": 83.21428571428571,
        "target_percent": 83
      },
      "top 1": {
        "count": 39,
        "achieved_percent": 13.928571428571429,
        "target_percent": 14
      },
      "top-k": {
        "count": 4,
        "achieved_percent": 1.4285714285714286,
        "target_percent": 1
      },
      "n-th ranked": {
        "count": 2,
        "achieved_percent": 0.7142857142857143,
        "target_percent": 0
      },
      "order with no limit": {
        "count": 2,
        "achieved_percent": 0.7142857142857143,
        "target_percent": 0
      }
    },
    "grouping": {
      "yes": {
        "count": 28,
        "achieved_percent": 10.0,
        "target_percent": 10
      }
    },
    "extras": {
      "none": {
        "count": 202,
        "achieved_percent": 72.14285714285714,
        "target_percent": 72
      },
      "distinct projection": {
        "count": 25,
        "achieved_percent": 8.928571428571429,
        "target_percent": 9
      },
      "ratio": {
        "count": 21,
        "achieved_percent": 7.5,
        "target_percent": 8
      },
      "conditional aggregate": {
        "count": 22,
        "achieved_percent": 7.857142857142857,
        "target_percent": 8
      },
      "negation": {
        "count": 0,
        "achieved_percent": 0.0,
        "target_percent": 3
      },
      "comparison of two named entities": {
        "count": 5,
        "achieved_percent": 1.7857142857142858,
        "target_percent": 2
      },
      "having": {
        "count": 2,
        "achieved_percent": 0.7142857142857143,
        "target_percent": 1
      },
      "existence": {
        "count": 3,
        "achieved_percent": 1.0714285714285714,
        "target_percent": 1
      }
    },
    "columns": {
      "one": {
        "count": 235,
        "achieved_percent": 83.92857142857143,
        "target_percent": 84
      },
      "two": {
        "count": 34,
        "achieved_percent": 12.142857142857142,
        "target_percent": 12
      },
      "three or more": {
        "count": 11,
        "achieved_percent": 3.9285714285714284,
        "target_percent": 4
      }
    },
    "depth": {
      "0-1": {
        "count": 196,
        "achieved_percent": 70.0,
        "target_percent": 70
      },
      "2": {
        "count": 56,
        "achieved_percent": 20.0,
        "target_percent": 20
      },
      "3-4": {
        "count": 28,
        "achieved_percent": 10.0,
        "target_percent": 10
      }
    }
  },
  "structure_counts": {
    "reused": 41,
    "new": 101
  },
  "checks": {
    "disjoint_instance_ids": true,
    "disjoint_query_parameter_pairs": true,
    "combined_max_per_structure": 5,
    "no_heldout_signature": true,
    "no_heldout_component_introduced": true,
    "first_batch_unchanged": true
  },
  "hints": {
    "with_hint": 256,
    "share": 0.9142857142857143
  },
  "first_batch_hashes": {
    "instances_v4_train.jsonl": "90aabd4910a78b558329cae81beeb67fae952b07a189033771042f01aaddb70d",
    "structures_v4_train.jsonl": "e517ff3ed01af1a010d52085bc84bf70c87e1d7fee08c1f0be9ff5985d2f0379",
    "questions_v4_train.jsonl": "9427dab24e1274840ab86a056f26b0f6929e6344b067901f56247976e3031b56",
    "new_structures.json": "780a390ea580032fad94ff203e6303267996bbf3f9217dfa91e7caee30fa2f2c"
  },
  "declared_shortfalls": [
    "Negation is held out entirely and omitted."
  ],
  "spec_arithmetic_note": {
    "first_requested": 320,
    "second_requested": 280,
    "combined_requested": 600,
    "stated_total_in_D2": 592,
    "interpretation": "Follow the explicit batch sizes; the stated total differs from their sum."
  },
  "verification": {
    "executed": 280,
    "matched": 280,
    "stable": 280,
    "rejections": {},
    "mismatched_ids": []
  }
}

## Second-batch individually authored question checkpoint

{
  "next_queue_index": 100,
  "instance_sha256": "c8da907295e67e154dd4cf0ed33135dfcff6859886b2c2cc9169702ff9e4e7dd",
  "batch_start": 0,
  "batch_written": 100,
  "questions_written": 100,
  "selected_instances": 280
}

## First v4 question set complete

{
  "selected_instances": 320,
  "questions_written": 320,
  "unique_instance_ids": 320,
  "complete_coverage": true,
  "heldout_questions_checked": 624,
  "heldout_exact_overlaps": [],
  "heldout_normalized_overlaps": [],
  "duplicate_questions": 0,
  "alias_mentions": [],
  "prohibited_vocabulary": [],
  "identical_subject_normalized_frames_within_structure": [],
  "max_questions_per_structure": 5,
  "selected_instances_unchanged": true
}

Questions were individually composed in the numbered v4 batch modules and polished after reading the rendered text. Literal and subject helpers bind data; no question-generation templates were used. Hints and selected instances were not changed. Frame checks are a mechanical screen, not an independent human naturalness review.

## Final turn checkpoint

{
  "first_batch_questions": 320,
  "second_batch_instances_verified": 280,
  "second_batch_questions": 100,
  "second_batch_questions_remaining": 180,
  "second_batch_checks": {
    "questions_written": 100,
    "selected_instances": 280,
    "questions_remaining": 180,
    "unique_instance_ids": 100,
    "all_written_ids_selected": true,
    "overlap_with_first_questions": [],
    "overlap_with_heldout_questions": [],
    "duplicate_questions": 0,
    "complete_coverage": false,
    "prohibited_vocabulary_or_aliases": [],
    "identical_normalized_frames_across_batches": []
  },
  "all_second_batch_mix_constraints_pass": true,
  "unit_tests": {
    "passed": 27,
    "failures": 0,
    "errors": 0
  },
  "first_batch_unchanged": true,
  "next_step": "Continue second-batch authoring from queue index 100, then audit complete coverage and overlap. First batch remains ready for training.",
  "spec_arithmetic_note": {
    "first_requested": 320,
    "second_requested": 280,
    "combined_requested": 600,
    "stated_total_in_D2": 592,
    "interpretation": "Follow the explicit batch sizes; the stated total differs from their sum."
  }
}

## Review step 1 replacement installation batch1

{
  "batch": "batch1",
  "lookups_replaced": 16,
  "questions_replaced": 16,
  "replacement_questions_pre_authored_for_pending_queue": 0,
  "untouched_instance_lines": 304,
  "untouched_question_lines": 304,
  "mix_cells_preserved": true,
  "rejections": {
    "all_null": 1
  }
}

## Review step 2 equal-range wording batch1

{
  "batch": "batch1",
  "equal_bound_questions_reworded": 13,
  "review_equal_bound_instances": 14,
  "written_equal_bound_questions_already_natural": 1,
  "instance_file_unchanged_by_wording": true,
  "untouched_question_lines_preserved": true
}

## First v4 question set complete

{
  "selected_instances": 320,
  "questions_written": 320,
  "unique_instance_ids": 320,
  "complete_coverage": true,
  "heldout_questions_checked": 624,
  "heldout_exact_overlaps": [],
  "heldout_normalized_overlaps": [],
  "duplicate_questions": 0,
  "alias_mentions": [],
  "prohibited_vocabulary": [],
  "identical_subject_normalized_frames_within_structure": [],
  "max_questions_per_structure": 5,
  "selected_instances_unchanged": true
}

Questions were individually composed in the numbered v4 batch modules and polished after reading the rendered text. Literal and subject helpers bind data; no question-generation templates were used. Hints and selected instances were not changed. Frame checks are a mechanical screen, not an independent human naturalness review.

## BATCH 1 FINAL

{
  "replacements": 16,
  "untouched_instances_byte_identical": true,
  "unchanged_instance_lines": 304,
  "changed_instance_lines": 16,
  "unaffected_questions_byte_identical": true,
  "same_mix_cells": true,
  "no_parameter_echo_lookups": true,
  "literal_scalar_parameter_equality_rejections": [
    "i_b01dff8c1a45cfb58f6b",
    "i_0d7dd124befdd5de6309",
    "i_a72932cb6e501e9bbbce"
  ],
  "literal_rule_passes_entire_batch": false,
  "declared_freeze_exceptions": [
    "i_b01dff8c1a45cfb58f6b",
    "i_0d7dd124befdd5de6309",
    "i_a72932cb6e501e9bbbce"
  ],
  "no_heldout_signature": true,
  "no_heldout_component_introduced": true,
  "heldout_question_overlaps": [],
  "duplicate_questions": 0,
  "questions_written": 320,
  "complete_coverage": true,
  "equal_bound_wording_remaining": [],
  "combined_max_per_structure": 5,
  "batch_ids_disjoint": true,
  "live_executed": 320,
  "live_matched": 320,
  "live_rejections": {}
}

## Review step 1 replacement installation batch2

{
  "batch": "batch2",
  "lookups_replaced": 8,
  "questions_replaced": 6,
  "replacement_questions_pre_authored_for_pending_queue": 2,
  "untouched_instance_lines": 272,
  "untouched_question_lines": 94,
  "mix_cells_preserved": true,
  "rejections": {}
}

## Review step 2 equal-range wording batch2

{
  "batch": "batch2",
  "equal_bound_questions_reworded": 14,
  "review_equal_bound_instances": 17,
  "written_equal_bound_questions_already_natural": 0,
  "instance_file_unchanged_by_wording": true,
  "untouched_question_lines_preserved": true
}

## Batch 2 targeted review fixes verified

{
  "replacements": 8,
  "untouched_instances_byte_identical": true,
  "unchanged_instance_lines": 272,
  "changed_instance_lines": 8,
  "unaffected_questions_byte_identical": true,
  "same_mix_cells": true,
  "no_parameter_echo_lookups": true,
  "literal_scalar_parameter_equality_rejections": [
    "i_4e8e8487db0d44adf93b",
    "i_e6f65abe7a1bd1e9e187",
    "i_048a356e7be989e10375",
    "i_66a892f22d60f658c9ee",
    "i_6b09f34b90c41096dcf3",
    "i_b1b0ed3d469489680211",
    "i_0e77b1272633d8ee6ff7",
    "i_0e8f36f2fc48fd50a87c",
    "i_fe21a3a6c2d06d731bf9"
  ],
  "literal_rule_passes_entire_batch": false,
  "declared_freeze_exceptions": [
    "i_4e8e8487db0d44adf93b",
    "i_e6f65abe7a1bd1e9e187",
    "i_048a356e7be989e10375",
    "i_66a892f22d60f658c9ee",
    "i_6b09f34b90c41096dcf3",
    "i_b1b0ed3d469489680211",
    "i_0e77b1272633d8ee6ff7",
    "i_0e8f36f2fc48fd50a87c",
    "i_fe21a3a6c2d06d731bf9"
  ],
  "no_heldout_signature": true,
  "no_heldout_component_introduced": true,
  "heldout_question_overlaps": [],
  "duplicate_questions": 0,
  "questions_written": 100,
  "complete_coverage": false,
  "equal_bound_wording_remaining": [],
  "combined_max_per_structure": 5,
  "batch_ids_disjoint": true,
  "live_executed": 280,
  "live_matched": 280,
  "live_rejections": {}
}

## Second-batch individually authored question checkpoint

{
  "next_queue_index": 200,
  "instance_sha256": "d05b1d1f5eb533a51877acb6bc317d2954b4c4a80a5d618fe2a92fda0566760d",
  "batch_start": 100,
  "batch_written": 100,
  "questions_written": 200,
  "selected_instances": 280
}

## Second-batch individually authored question checkpoint

{
  "next_queue_index": 280,
  "instance_sha256": "d05b1d1f5eb533a51877acb6bc317d2954b4c4a80a5d618fe2a92fda0566760d",
  "batch_start": 200,
  "batch_written": 80,
  "questions_written": 280,
  "selected_instances": 280
}

## Batch 2 targeted review fixes verified

{
  "replacements": 8,
  "untouched_instances_byte_identical": true,
  "unchanged_instance_lines": 272,
  "changed_instance_lines": 8,
  "unaffected_questions_byte_identical": true,
  "same_mix_cells": true,
  "no_parameter_echo_lookups": true,
  "literal_scalar_parameter_equality_rejections": [
    "i_4e8e8487db0d44adf93b",
    "i_e6f65abe7a1bd1e9e187",
    "i_048a356e7be989e10375",
    "i_66a892f22d60f658c9ee",
    "i_6b09f34b90c41096dcf3",
    "i_b1b0ed3d469489680211",
    "i_0e77b1272633d8ee6ff7",
    "i_0e8f36f2fc48fd50a87c",
    "i_fe21a3a6c2d06d731bf9"
  ],
  "literal_rule_passes_entire_batch": false,
  "declared_freeze_exceptions": [
    "i_4e8e8487db0d44adf93b",
    "i_e6f65abe7a1bd1e9e187",
    "i_048a356e7be989e10375",
    "i_66a892f22d60f658c9ee",
    "i_6b09f34b90c41096dcf3",
    "i_b1b0ed3d469489680211",
    "i_0e77b1272633d8ee6ff7",
    "i_0e8f36f2fc48fd50a87c",
    "i_fe21a3a6c2d06d731bf9"
  ],
  "no_heldout_signature": true,
  "no_heldout_component_introduced": true,
  "heldout_question_overlaps": [],
  "duplicate_questions": 0,
  "questions_written": 280,
  "complete_coverage": true,
  "equal_bound_wording_remaining": [],
  "combined_max_per_structure": 5,
  "batch_ids_disjoint": true,
  "live_executed": 280,
  "live_matched": 280,
  "live_rejections": {}
}

## Final reviewed question-set audit

{
  "batches": [
    {
      "batch": "batch1",
      "questions_written": 320,
      "instances": 320,
      "complete_coverage": true,
      "duplicate_ids": 0,
      "heldout_overlaps": [],
      "alias_mentions": [],
      "prohibited_vocabulary": [],
      "replacement_field_wording_mismatches": [],
      "lookup_scalar_parameter_echo_ids": [],
      "literal_scalar_parameter_equality_rejections": [
        "i_b01dff8c1a45cfb58f6b",
        "i_0d7dd124befdd5de6309",
        "i_a72932cb6e501e9bbbce"
      ],
      "equal_bound_wording_remaining": [],
      "raw_bytes_preserved_for_untouched_instances": true,
      "raw_bytes_preserved_for_untouched_written_questions": true,
      "hints_with_hint": 291,
      "hint_share": 0.909375
    },
    {
      "batch": "batch2",
      "questions_written": 280,
      "instances": 280,
      "complete_coverage": true,
      "duplicate_ids": 0,
      "heldout_overlaps": [],
      "alias_mentions": [],
      "prohibited_vocabulary": [],
      "replacement_field_wording_mismatches": [],
      "lookup_scalar_parameter_echo_ids": [],
      "literal_scalar_parameter_equality_rejections": [
        "i_4e8e8487db0d44adf93b",
        "i_e6f65abe7a1bd1e9e187",
        "i_048a356e7be989e10375",
        "i_66a892f22d60f658c9ee",
        "i_6b09f34b90c41096dcf3",
        "i_b1b0ed3d469489680211",
        "i_0e77b1272633d8ee6ff7",
        "i_0e8f36f2fc48fd50a87c",
        "i_fe21a3a6c2d06d731bf9"
      ],
      "equal_bound_wording_remaining": [],
      "raw_bytes_preserved_for_untouched_instances": true,
      "raw_bytes_preserved_for_untouched_written_questions": true,
      "hints_with_hint": 256,
      "hint_share": 0.9142857142857143
    }
  ],
  "combined_questions": 600,
  "duplicate_questions_across_batches": 0,
  "duplicate_instance_ids_across_batches": 0,
  "identical_normalized_sentence_frames_same_structure": []
}

## Final reviewed question-set audit

{
  "batches": [
    {
      "batch": "batch1",
      "questions_written": 320,
      "instances": 320,
      "complete_coverage": true,
      "duplicate_ids": 0,
      "heldout_overlaps": [],
      "alias_mentions": [],
      "prohibited_vocabulary": [],
      "replacement_field_wording_mismatches": [],
      "lookup_scalar_parameter_echo_ids": [],
      "literal_scalar_parameter_equality_rejections": [
        "i_b01dff8c1a45cfb58f6b",
        "i_0d7dd124befdd5de6309",
        "i_a72932cb6e501e9bbbce"
      ],
      "equal_bound_wording_remaining": [],
      "raw_bytes_preserved_for_untouched_instances": true,
      "raw_bytes_preserved_for_untouched_written_questions": true,
      "hints_with_hint": 291,
      "hint_share": 0.909375
    },
    {
      "batch": "batch2",
      "questions_written": 280,
      "instances": 280,
      "complete_coverage": true,
      "duplicate_ids": 0,
      "heldout_overlaps": [],
      "alias_mentions": [],
      "prohibited_vocabulary": [],
      "replacement_field_wording_mismatches": [],
      "lookup_scalar_parameter_echo_ids": [],
      "literal_scalar_parameter_equality_rejections": [
        "i_4e8e8487db0d44adf93b",
        "i_e6f65abe7a1bd1e9e187",
        "i_048a356e7be989e10375",
        "i_66a892f22d60f658c9ee",
        "i_6b09f34b90c41096dcf3",
        "i_b1b0ed3d469489680211",
        "i_0e77b1272633d8ee6ff7",
        "i_0e8f36f2fc48fd50a87c",
        "i_fe21a3a6c2d06d731bf9"
      ],
      "equal_bound_wording_remaining": [],
      "raw_bytes_preserved_for_untouched_instances": true,
      "raw_bytes_preserved_for_untouched_written_questions": true,
      "hints_with_hint": 256,
      "hint_share": 0.9142857142857143
    }
  ],
  "combined_questions": 600,
  "duplicate_questions_across_batches": 0,
  "duplicate_instance_ids_across_batches": 0,
  "identical_normalized_sentence_frames_same_structure": []
}

## Native timestamp replacement verification

{
  "date_replacements_corrected": 6,
  "all_reproduced": true,
  "source": "https://neo4j.com/docs/api/python-driver/current/types/temporal.html",
  "evidence": "creation_date_encoding_audit.json records the live native-vs-string formatting difference. Native property projection removes the unnecessary cast."
}

## BATCH 1 FINAL

{
  "replacements": 16,
  "untouched_instances_byte_identical": true,
  "unchanged_instance_lines": 304,
  "changed_instance_lines": 16,
  "unaffected_questions_byte_identical": true,
  "same_mix_cells": true,
  "no_parameter_echo_lookups": true,
  "literal_scalar_parameter_equality_rejections": [
    "i_b01dff8c1a45cfb58f6b",
    "i_0d7dd124befdd5de6309",
    "i_a72932cb6e501e9bbbce"
  ],
  "literal_rule_passes_entire_batch": false,
  "declared_freeze_exceptions": [
    "i_b01dff8c1a45cfb58f6b",
    "i_0d7dd124befdd5de6309",
    "i_a72932cb6e501e9bbbce"
  ],
  "no_heldout_signature": true,
  "no_heldout_component_introduced": true,
  "heldout_question_overlaps": [],
  "duplicate_questions": 0,
  "questions_written": 320,
  "complete_coverage": true,
  "equal_bound_wording_remaining": [],
  "combined_max_per_structure": 5,
  "batch_ids_disjoint": true,
  "live_executed": 320,
  "live_matched": 320,
  "live_rejections": {}
}

## Batch 2 targeted review fixes verified

{
  "replacements": 8,
  "untouched_instances_byte_identical": true,
  "unchanged_instance_lines": 272,
  "changed_instance_lines": 8,
  "unaffected_questions_byte_identical": true,
  "same_mix_cells": true,
  "no_parameter_echo_lookups": true,
  "literal_scalar_parameter_equality_rejections": [
    "i_4e8e8487db0d44adf93b",
    "i_e6f65abe7a1bd1e9e187",
    "i_048a356e7be989e10375",
    "i_66a892f22d60f658c9ee",
    "i_6b09f34b90c41096dcf3",
    "i_b1b0ed3d469489680211",
    "i_0e77b1272633d8ee6ff7",
    "i_0e8f36f2fc48fd50a87c",
    "i_fe21a3a6c2d06d731bf9"
  ],
  "literal_rule_passes_entire_batch": false,
  "declared_freeze_exceptions": [
    "i_4e8e8487db0d44adf93b",
    "i_e6f65abe7a1bd1e9e187",
    "i_048a356e7be989e10375",
    "i_66a892f22d60f658c9ee",
    "i_6b09f34b90c41096dcf3",
    "i_b1b0ed3d469489680211",
    "i_0e77b1272633d8ee6ff7",
    "i_0e8f36f2fc48fd50a87c",
    "i_fe21a3a6c2d06d731bf9"
  ],
  "no_heldout_signature": true,
  "no_heldout_component_introduced": true,
  "heldout_question_overlaps": [],
  "duplicate_questions": 0,
  "questions_written": 280,
  "complete_coverage": true,
  "equal_bound_wording_remaining": [],
  "combined_max_per_structure": 5,
  "batch_ids_disjoint": true,
  "live_executed": 280,
  "live_matched": 280,
  "live_rejections": {}
}

## Final reviewed question-set audit

{
  "batches": [
    {
      "batch": "batch1",
      "questions_written": 320,
      "instances": 320,
      "complete_coverage": true,
      "duplicate_ids": 0,
      "heldout_overlaps": [],
      "alias_mentions": [],
      "prohibited_vocabulary": [],
      "replacement_field_wording_mismatches": [],
      "lookup_scalar_parameter_echo_ids": [],
      "literal_scalar_parameter_equality_rejections": [
        "i_b01dff8c1a45cfb58f6b",
        "i_0d7dd124befdd5de6309",
        "i_a72932cb6e501e9bbbce"
      ],
      "equal_bound_wording_remaining": [],
      "raw_bytes_preserved_for_untouched_instances": true,
      "raw_bytes_preserved_for_untouched_written_questions": true,
      "hints_with_hint": 291,
      "hint_share": 0.909375
    },
    {
      "batch": "batch2",
      "questions_written": 280,
      "instances": 280,
      "complete_coverage": true,
      "duplicate_ids": 0,
      "heldout_overlaps": [],
      "alias_mentions": [],
      "prohibited_vocabulary": [],
      "replacement_field_wording_mismatches": [],
      "lookup_scalar_parameter_echo_ids": [],
      "literal_scalar_parameter_equality_rejections": [
        "i_4e8e8487db0d44adf93b",
        "i_e6f65abe7a1bd1e9e187",
        "i_048a356e7be989e10375",
        "i_66a892f22d60f658c9ee",
        "i_6b09f34b90c41096dcf3",
        "i_b1b0ed3d469489680211",
        "i_0e77b1272633d8ee6ff7",
        "i_0e8f36f2fc48fd50a87c",
        "i_fe21a3a6c2d06d731bf9"
      ],
      "equal_bound_wording_remaining": [],
      "raw_bytes_preserved_for_untouched_instances": true,
      "raw_bytes_preserved_for_untouched_written_questions": true,
      "hints_with_hint": 256,
      "hint_share": 0.9142857142857143
    }
  ],
  "combined_questions": 600,
  "duplicate_questions_across_batches": 0,
  "duplicate_instance_ids_across_batches": 0,
  "identical_normalized_sentence_frames_same_structure": []
}

## Final handoff after all review corrections

[
  {
    "batch": "batch1",
    "status": "batch 1 FINAL; requested review repairs verified; frozen aggregate equality exceptions declared",
    "questions": 320,
    "replacements": 16,
    "equal_bound_ranges_resolved": 14,
    "live_replay": {
      "executed": 320,
      "matched": 320,
      "rejections": {}
    },
    "literal_scalar_equality_frozen_exceptions": 3,
    "mix_preserved": true,
    "unit_tests": {
      "passed": 28,
      "failures": 0,
      "errors": 0
    }
  },
  {
    "batch": "batch2",
    "status": "batch 2 complete; requested review repairs verified; frozen aggregate equality exceptions declared",
    "questions": 280,
    "replacements": 8,
    "equal_bound_ranges_resolved": 17,
    "live_replay": {
      "executed": 280,
      "matched": 280,
      "rejections": {}
    },
    "literal_scalar_equality_frozen_exceptions": 9,
    "mix_preserved": true,
    "unit_tests": {
      "passed": 28,
      "failures": 0,
      "errors": 0
    }
  }
]
