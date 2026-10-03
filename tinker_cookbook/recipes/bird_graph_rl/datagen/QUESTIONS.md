# Questions for the team — choices applied without blocking

1. B4 specifies a minority of numeric-ID anchors but no quota for single-column
   statistics. The regenerated dataset has diverse semantic aliases and entity
   lists/count groupings, yet most results are scalar. I have kept plausible
   scalar questions instead of adding redundant name columns to inflate shape
   diversity. Should the next revision require an explicit minimum fraction of
   naturally useful multi-column summaries? The measured shares are in report.json.
2. A1 groups different properties on a label together. This is implemented, but
   different missingness and stored-counter semantics remain within one structure.
   Scientific novelty tags are exact for these defined components, not a proof of
   unseen statistical meaning. Is that the desired interpretation of the figure?
3. B3 removes the previous difference-of-aggregates family because score minus
   absolute score is contrived. That entire extras class disappears, explicitly
   reported by component. A future visitor-friendly family could compare stored
   up-vote and down-vote totals; I have not added it merely to preserve a count.
4. B5 uses original source names. The export schema confirms that Posts uses the
   CreaionDate typo; other creation dates use CreationDate. This is applied in
   hints, which also describe preview truncation. Pilot JSON contains no hint,
   while the corresponding instance may carry one; B5 supersedes A5's indecision.
5. Absolute runtime determinism conflicts with measuring wall time and rejecting
   queries beyond five seconds under variable machine load. Semantic artifacts
   are deterministic on an unchanged graph; times and timeout acceptance are not.
6. Naturalness and B6 are human quality requirements, not execution properties.
   Intents and individually authored questions are supplied, but independent
   human ambiguity/grammar review is still needed before scaling. Quoted real
   names/titles may contain camel case or otherwise banned ordinary words; those
   data literals are preserved and excluded from syntax-token validation.
