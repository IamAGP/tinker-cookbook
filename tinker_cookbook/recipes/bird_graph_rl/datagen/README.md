## Checkpoint (b)

B3: every surviving candidate has an ordinary visitor intent; matched-combination
counts and the contrived score-minus-absolute-score statistic are removed.
Distinct entity groupings and thresholded groupings are separate replacement
structures with distinct aggregation target labels. Exact removals by path,
aggregation and extras are in `out/naturalness.json`. Filtering precedes split.

B4 implementation now selects names, titles, badge names and creation dates
for most anchors and returns names/text with scores or entity counts. All
statistics deduplicate ENTITY identities before aggregation. Next: wire graph
parameter sampling and semantic sort keys; regenerate and independently replay.

# Amendment checkpoint

A1–A3 implemented and unit-tested: uniform label granularity; canonical branches,
schema directions and subtype filters; exact component and combination holdouts.
The old output counts below describe the PRE-AMENDMENT run and must not be used
for the amended experiment. See `out/checkpoint_a.json`.

Next: B3 naturalness filtering; B4 anchors and returns; regenerate and replay;
B5 hints; B1/B2/B6 pilot rewrite.

# Query-first data generation (stage A)

Run from the repository root, using only installed dependencies:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -o cache_dir=tinker_cookbook/recipes/bird_graph_rl/datagen/.pytest_cache tinker_cookbook/recipes/bird_graph_rl/datagen
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tinker_cookbook.recipes.bird_graph_rl.datagen.generate
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tinker_cookbook.recipes.bird_graph_rl.datagen.inspect
```

Connection settings are loaded from the repository-root `.env` with `python-dotenv`.
Only `BIRD_NEO4J_URI`, `BIRD_NEO4J_USER`, and `BIRD_NEO4J_PASSWORD` are used; none
are logged or copied into artifacts. Graph queries use explicit transactions in
`READ_ACCESS` sessions and are rolled back on exit. Mutation/procedure clauses are
also blocked. No graph configuration is changed. No evaluation artifacts, BIRD
question files, object storage, or training-run directories are accessed.

The graph schema comes exclusively from `DATA_HANDOFF.md` sections 3–4 and the
`SYSTEM_PROMPT` text in `baseline_eval.py`. Connection and timeout behavior were
checked against the official maintained [Neo4j Python driver manual](https://neo4j.com/docs/python-manual/current/transactions/).
Read routing alone is not an access-control guarantee, which is why the generator
also restricts its own query text and never calls procedures.

## Structure definition and generation

`structures.py` enumerates 32 schema-valid patterns and 532 distinct canonical
six-tuples. Paths include zero through four edges, direction-sensitive self-joins,
and shared-root branches. The canonical JSON signature preserves ordered node
labels and directed edges; sorts the filter-kind multiset; and deduplicates/sorts
the extras set. SHA-256 of this signature gives the stable structure ID. Rendering
modes with the same six-tuple are deduplicated. Parameter values never enter a
signature. No artificial template index or output alias distinguishes structures.

Roots are sampled from graph-derived identity/numeric pools, using deterministic
sorted retrieval followed by a per-path and per-structure seeded shuffle. Pools
are conditioned on the first path edge, not on the evaluation distribution. String
prefixes are read from matched graph text; both numeric range bounds originate in
actual measurements. Calendar-year bounds are sampled from matched creation years. Unique member names are established by a
graph-wide count, including exact case-sensitive duplicate names. Comparison
queries draw two distinct unique names.

Each structure considers up to 96 distinct parameter sets by default and retains
at most twelve. Empty/oversized/all-null results, errors, slow queries, and tied
primary sort keys at a truncation boundary are rejected. Every kept structure has
at least two different accepted answers. If the first twelve answers are equal,
sampling continues and replaces one with the first differing answer. If no such
answer is found, the entire structure is dropped. Zero counts are valid answers
under the specified row/non-null rules; a structure returning only zero is dropped.

`ORDER BY` lists use a unique entity ID as the final key after `DISTINCT` or
grouping. Top-k, argmax, and argmin independently execute a k+1 probe and compare the
primary metric across the cut, even though a secondary ID already resolves ties.
All artifact answers use order-insensitive **multiset** comparison with named
columns (duplicates remain significant). Queries never silently LIMIT oversized
answers: the reader collects 201 rows and rejects the entire instance.

## Choices where the spec is underspecified

1. **Branches:** hop count is the total number of relationship edges, including
   both arms. This measures join complexity consistently; longest-arm length
   would understate branching complexity. Node positions and directed edges are
   explicit in the path portion of the signature.
2. **Instance holdout:** select about 20% of retained structures within each hop
   stratum as `heldout_structure`. Reserve up to two instances per remaining structure
   for `heldout_instance`, leaving at least two training instances. Their complete
   parameter dictionaries differ from all training dictionaries for that
   structure. Structure splits happen after filtering, so rejected structures
   cannot distort the observed split. Holdout selection does not use answers.
3. **Timing/determinism:** the five-second instance limit includes client execution,
   retrieval, and transaction cleanup. Neo4j also receives a five-second server
   timeout. Identity/name pool scans use a 30-second timeout and are sampling
   operations rather than training instances. IDs, sampling, splitting, queries,
   and scalar answers are deterministic for a fixed seed and unchanged graph;
   measured runtimes and timeout-dependent acceptance cannot be deterministic
   under changes in machine load. This is an unavoidable qualification to the
   spec's absolute determinism statement.
4. **Names and parameters:** name filters require uniqueness over the complete
   current graph, not merely sampled roots. Cypher equality/substring tests are
   case-sensitive. Entity names/IDs, numeric range endpoints, calendar-year bounds, and text
   prefixes come from the graph. LIMIT sizes and HAVING cardinality thresholds
   are query-control parameters selected with the seeded RNG.
5. **Negative controls:** no-existence and difference-of-aggregates structures
   are deliberately attempted. Many are constant on particular paths and are
   dropped rather than relabelled into supposedly new structures.
6. **Answers and pilot:** rows are dictionaries of named scalar return columns;
   no nodes, relationships, date objects, or hidden answer columns are serialized.
   Stage-B questions request exactly those aliases, while describing the domain
   in ordinary language rather than using graph identifiers. The pilot is a
   manually authored set, not generated by a paraphrase template or model.

## Outputs and verification

All generated evidence lives under ignored `out/`:

- `structures.jsonl`, `instances.jsonl`, `report.json`: specified stage-A artifacts.
- `debug.log`: per-structure outcome and individual rejections, without connection
  settings; retained to support diagnosis.
- `inspection.jsonl`, `inspection_summary.json`: independent sample re-execution
  plus exhaustive artifact integrity checks.
- `pilot_questions.jsonl`: 60 manually written questions spanning all hop counts.

`inspect.py` checks every instance's row limit, runtime, scalar non-nullness,
parameter uniqueness, structure signature/rendering, answer variation, and split
isolation. It then independently re-executes twelve examples per hop and adds any
unrepresented rendering modes, checks exact answers, probes truncation boundaries,
and verifies names. This supplements the database-free colocated unit tests.

Final measured counts and pilot details are recorded below after execution.

The pilot can be reproduced with:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tinker_cookbook.recipes.bird_graph_rl.datagen.pilot
```

The pilot interprets the prohibition on property names literally: contributions,
remarks, point totals, standing points, and member numbers describe the domain
without `Post`, `Comment`, `score`, `reputation`, or `userId`. Return aliases are
quoted exactly. This constraint can reduce semantic precision at scale; a full
stage-B ambiguity check must validate these synonyms against the intended metric.

Redundant predicates are omitted: a path already containing a remark attachment
does not get an existence test for that same attachment. Subtype filters are
used on generic contributions rather than on already fixed subtypes. Argmax
returns the winning entity and measurement, whereas max returns only the scalar
measurement; both selection directions receive the strict boundary-tie check.


## Final measured result (seed 20261003)

All targets were met: **469 retained structures and 5,590 verified instances**
from 532 enumerated structures. Exactly 72/469 (15.35%) have at most one hop.
No graph writes, evaluation access, dependency installation, commit, or push was
performed.

| Hops | Structures | Instances |
|---|---:|---:|
| 0 | 16 | 181 |
| 1 | 56 | 672 |
| 2 | 151 | 1,812 |
| 3 | 122 | 1,449 |
| 4 | 124 | 1,476 |

Structure split: 376 training structures, 93 held-out structures.
Instance split: 3,723 train, 751 heldout_instance, 1,116 heldout_structure.
One small training structure reserves one rather than two instances so that at
least two remain in training. Parameter-set holdouts share their parent structure
with training; structure holdouts never do.

Structures by aggregation: none 112, count 132, count distinct 24, sum 85, avg 65,
min 24, max 27. Corresponding instance counts: none 1,326, count 1,575, count
distinct 288, sum 1,020, avg 769, min 288, max 324.

Structures by extra: existence 6 (including 3 negated), negation 3, percentage 8,
difference of aggregates 5, named comparison 16, HAVING 21. Instance counts:
existence 72, negation 36, percentage 96, difference 60, comparison 192, HAVING 243.
Extras overlap; these are membership counts, not a partition.

Rejections: row count 2,328; all-null 1,831; primary cut-boundary tie 821;
constant answer 4,095 accepted observations discarded across rejected structures;
no sampled parameters 2 structures. Execution errors, time-limit failures,
unstable results, ambiguous names, and sampling errors were all zero in the final
run. Unique-name sampling prevents ambiguous names from reaching execution.
An earlier percentage denominator error was reproduced and fixed; the diagnostic
is retained in `out/ratio_diagnosis.json`. Original failure `/ by zero` is converted
to an all-null answer when no routes exist, then rejected by the ordinary rule.

**Validation:** 16 database-free unit tests passed. Exhaustive checks of every
artifact instance passed. **127 independently re-executed examples** matched
exactly, covering all 32 paths, all 24 rendering modes, all five hop counts,
and **all 60 pilot bindings**. Inspection also rechecks unique names and primary
sort-key cut boundaries. The pilot has twelve individually authored prompts per
hop count and names the exact requested columns. A case-insensitive whole-word
lexical audit found no labels, relationship identifiers, or property names in
its 60 questions. Prompts and bindings were manually reviewed for requested
aggregation, ordering, missingness, repeated-route weighting, and scope.

## Stage B scaling limitations

A loop that substitutes parameters into these 60 prompts would violate the
no-paraphrase-template requirement and encourage memorisation. Scaling needs
fresh questions plus independent ambiguity checks, particularly for branched
paths, distinct entities versus repeated routes, snapshot counters versus derived
counts, ratios' denominators, numeric/calendar interval inclusivity, and missing
values. Requests for a scalar maximum and requests for its winning entity must
remain distinct. Human-facing synonyms required by the literal identifier ban
need consistency checks: standing points and point totals are different metrics.
Answers must be bound to the actual requested return columns and compared with
the declared multiset semantics; a model's incidental response order must not
change scoring.

The current artifacts depend on an unchanged graph. Graph edits invalidate saved
answers, uniqueness checks, and cut-boundary proofs, and therefore require
regeneration. Runtime fields and five-second acceptance cannot be perfectly
reproducible on a machine under changing load. These are explicit limitations,
not evidence that any current target was missed. There is no billed-model stage
or full stage-B natural-language generation in this implementation.
