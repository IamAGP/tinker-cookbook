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
   stratum as `heldout_structure`. Reserve two instances per remaining structure
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
