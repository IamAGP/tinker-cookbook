"""One-off Lambda: store FULL reference rows for the questions whose rows were capped at 200.

reference_answers.json capped stored rows at 200, which makes exact row-level F1 impossible for
11 of the 186 questions — and five of those are in the set that partial credit rescues. This
re-executes just those gold SQLs on the original SQLite file and writes their complete result
sets, so the reward needs no approximate branch.
"""
import json
import os
import sqlite3
import time

import boto3

SRC_BUCKET, SRC_KEY, OUT_BUCKET = os.environ["SRC_BUCKET"], os.environ["SRC_KEY"], os.environ["OUT_BUCKET"]
REF_KEY = "codebase_community/gold/reference_answers.json"
OUT_KEY = "codebase_community/gold/reference_rows_full.json"
DB, T0 = "/tmp/db.sqlite", time.time()


def log(m):
    print(f"[{time.time() - T0:6.1f}s] {m}", flush=True)


def handler(event, context):
    s3 = boto3.client("s3")
    s3.download_file(SRC_BUCKET, SRC_KEY, DB)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    ref = json.loads(s3.get_object(Bucket=OUT_BUCKET, Key=REF_KEY)["Body"].read())
    items = [r for r in ref["results"]["corrected_20251106"] if r.get("truncated")]
    log(f"{len(items)} truncated questions to re-execute")
    out, total = {}, 0
    for r in items:
        t = time.time()
        rows = con.execute(r["SQL"]).fetchall()
        out[str(r["question_id"])] = {"n_rows": len(rows), "rows": [list(x) for x in rows]}
        total += len(rows)
        log(f"  q{r['question_id']}: {len(rows)} rows (stored n_rows={r['n_rows']}) in {time.time()-t:.1f}s")
        assert len(rows) == r["n_rows"], f"row count drift on q{r['question_id']}"
    body = json.dumps(out, default=str).encode()
    s3.put_object(Bucket=OUT_BUCKET, Key=OUT_KEY, Body=body, ContentType="application/json")
    log(f"wrote s3://{OUT_BUCKET}/{OUT_KEY}  {len(body)/1e6:.1f} MB, {total} rows")
    return {"questions": len(out), "total_rows": total, "bytes": len(body)}
