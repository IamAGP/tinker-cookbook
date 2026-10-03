"""Reward for RL: deterministic partial credit from executed rows.

The baseline scorer is binary — the returned rows either match the reference or they do not.
That is the right primary *metric*, but it is a poor training *reward*: a group in which every
sample is wrong has zero advantage spread, so group-relative RL learns nothing from it, and
52 of the 186 questions were never solved in either baseline run.

`partial_credit` keeps the binary metric's definition of success (it returns exactly 1.0 when
and only when the strict scorer would) while grading near misses by row-level F1. It is
deterministic, computed from the database, and needs no judge.

Deliberately NOT included: credit for merely mentioning the right values somewhere. An earlier
project on a different graph found that an entity-overlap term taught the policy to name
entities without computing anything. Row-level F1 cannot be farmed that way, because a row only
counts when every one of its values matches.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

import boto3

from tinker_cookbook.recipes.bird_graph_rl.baseline_eval import load_references, row_key

FULL_ROWS_KEY = "codebase_community/gold/reference_rows_full.json"


def load_references_exact(reference_uri: str, gold_set: str = "corrected_20251106") -> list[dict[str, Any]]:
    """References with complete rows, so row-level F1 is exact for every question.

    `reference_answers.json` caps stored rows at 200, which left 11 questions unscoreable
    exactly. `reference_rows_full.json` holds their complete result sets; this merges them in
    and clears the `truncated` flag, so the approximate branch below is never taken.
    """
    refs = load_references(reference_uri, gold_set)
    bucket = reference_uri.removeprefix("s3://").split("/", 1)[0]
    full = json.loads(boto3.client("s3").get_object(Bucket=bucket, Key=FULL_ROWS_KEY)["Body"].read())
    for r in refs:
        entry = full.get(str(r["question_id"]))
        if entry is not None:
            assert entry["n_rows"] == r["n_rows"], f"row-count drift on q{r['question_id']}"
            r["rows"], r["truncated"] = entry["rows"], False
    return refs


def _f1(got: list[tuple[str, ...]], want: list[tuple[str, ...]]) -> float:
    """Multiset F1 over whole rows."""
    if not got and not want:
        return 1.0
    if not got or not want:
        return 0.0
    gc, wc = Counter(got), Counter(want)
    overlap = sum(min(gc[k], wc[k]) for k in gc.keys() & wc.keys())
    if overlap == 0:
        return 0.0
    precision, recall = overlap / len(got), overlap / len(want)
    return 2 * precision * recall / (precision + recall)


def partial_credit(model_rows: list[list[Any]], ref: dict[str, Any]) -> dict[str, float]:
    """Graded reward in [0, 1]; 1.0 exactly when the strict scorer would also say correct.

    `ref` is one entry of reference_answers.json: `rows` (capped at 200), `n_rows`, `truncated`.
    Use `load_references_exact` so every reference carries complete rows; the truncated branch
    below is then dead code, kept only as a fallback for a reference built without it.
    """
    ref_rows: list[list[Any]] = ref.get("rows") or []
    ref_n = int(ref.get("n_rows", len(ref_rows)))
    truncated = bool(ref.get("truncated"))
    got = [row_key(r) for r in model_rows]
    want = [row_key(r) for r in ref_rows]

    if truncated:
        got_set = set(got)
        containment = sum(1 for w in want if w in got_set) / len(want) if want else 0.0
        if not model_rows:
            count_ratio = 0.0
        else:
            count_ratio = min(len(model_rows), ref_n) / max(len(model_rows), ref_n)
        score = containment * count_ratio
        strict = 1.0 if (len(model_rows) == ref_n and containment == 1.0) else 0.0
        return {"reward": 1.0 if strict else min(score, 0.99), "strict": strict, "approximate": 1.0}

    score = _f1(got, want)
    strict = 1.0 if sorted(got) == sorted(want) else 0.0
    # F1 can reach 1.0 only when the multisets match, so the two agree by construction;
    # clamp anyway so a reward of exactly 1.0 always means "strictly correct".
    return {"reward": score if strict else min(score, 0.99), "strict": strict, "approximate": 0.0}
