"""One-off Lambda: execute BIRD gold SQL for codebase_community on the SQLite file in S3.

Produces the execution-verified reference answers plus fragility flags:
error / empty result / LIMIT-1 tie (heuristic) / answer changed between mini-dev and the
Nov-2025 corrected release. Result rows are capped at ROW_CAP; the full row count and an
order-insensitive hash of ALL rows are always recorded.
"""
import hashlib
import json
import os
import re
import sqlite3
import time

import boto3

SRC_BUCKET, SRC_KEY, OUT_BUCKET = os.environ["SRC_BUCKET"], os.environ["SRC_KEY"], os.environ["OUT_BUCKET"]
GOLD = {"corrected_20251106": "codebase_community/gold/dev_20251106_codebase_community.json",
        "mini_dev": "codebase_community/gold/mini_dev_codebase_community.json"}
DB, ROW_CAP, QUERY_BUDGET_S, T0 = "/tmp/db.sqlite", 200, 20.0, time.time()
TIE_RE = re.compile(r"^(?P<head>\s*SELECT\s+)(?P<cols>.+?)(?P<rest>\s+FROM\s+.+?)\s+ORDER\s+BY\s+(?P<key>.+?)"
                    r"(?P<dir>\s+(?:ASC|DESC))?\s+LIMIT\s+1\s*;?\s*$", re.I | re.S)


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def run(con, sql):
    start = time.time()
    con.set_progress_handler(lambda: 1 if time.time() - start > QUERY_BUDGET_S else 0, 100000)
    try:
        rows = con.execute(sql).fetchall()
        canon = sorted(json.dumps(r, default=str) for r in rows)
        return {"ok": True, "n_rows": len(rows), "rows": [list(r) for r in rows[:ROW_CAP]],
                "truncated": len(rows) > ROW_CAP, "hash_unordered": hashlib.sha256("\n".join(canon).encode()).hexdigest()[:16],
                "seconds": round(time.time() - start, 3)}
    except Exception as e:  # noqa: BLE001 - record every failure mode verbatim
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "seconds": round(time.time() - start, 3)}
    finally:
        con.set_progress_handler(None, 0)


def tie_check(con, sql):
    """For `... ORDER BY k [dir] LIMIT 1`: fetch the top 2 sort keys; equal keys => answer is tie-dependent."""
    m = TIE_RE.match(sql)
    if not m or re.search(r"\bLIMIT\b", m.group("rest"), re.I):
        return None
    probe = f"SELECT ({m.group('key')}) AS __k{m.group('rest')} ORDER BY __k{m.group('dir') or ''} LIMIT 2"
    r = run(con, probe)
    if not r["ok"]:
        return {"checked": False, "reason": r["error"][:120]}
    keys = [row[0] for row in r["rows"]]
    return {"checked": True, "top_keys": keys, "tied": len(keys) == 2 and keys[0] == keys[1]}


def handler(event, context):
    s3 = boto3.client("s3")
    s3.download_file(SRC_BUCKET, SRC_KEY, DB)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    log("db ready")
    out, summary = {}, {}
    for name, key in GOLD.items():
        items = json.loads(s3.get_object(Bucket=OUT_BUCKET, Key=key)["Body"].read())
        res = []
        for i, q in enumerate(items, 1):
            r = run(con, q["SQL"])
            r.update({k: q.get(k) for k in ("question_id", "question", "evidence", "SQL", "difficulty")})
            r["tie"] = tie_check(con, q["SQL"]) if r["ok"] else None
            res.append(r)
            if i % 25 == 0:
                log(f"{name}: {i}/{len(items)}")
        out[name] = res
        summary[name] = {"questions": len(res), "errors": sum(not r["ok"] for r in res),
                         "empty": sum(r["ok"] and r["n_rows"] == 0 for r in res),
                         "truncated": sum(bool(r.get("truncated")) for r in res),
                         "limit1_checked": sum(bool(r["tie"] and r["tie"].get("checked")) for r in res),
                         "limit1_tied": sum(bool(r["tie"] and r["tie"].get("tied")) for r in res),
                         "slowest_s": max(r["seconds"] for r in res)}
        log(f"{name}: {summary[name]}")
    by_id = {r["question_id"]: r for r in out["corrected_20251106"]}
    diff = []
    for r in out["mini_dev"]:
        c = by_id.get(r["question_id"])
        if c is None:
            diff.append({"question_id": r["question_id"], "status": "absent_in_corrected"})
            continue
        sql_changed = " ".join(r["SQL"].split()) != " ".join(c["SQL"].split())
        ans_changed = r.get("hash_unordered") != c.get("hash_unordered")
        if sql_changed or ans_changed:
            diff.append({"question_id": r["question_id"], "question": r["question"], "sql_changed": sql_changed,
                         "answer_changed": ans_changed, "mini_rows": r.get("rows", [])[:3],
                         "corrected_rows": c.get("rows", [])[:3]})
    summary["mini_vs_corrected"] = {"overlap": sum(r["question_id"] in by_id for r in out["mini_dev"]),
                                    "sql_changed": sum(d.get("sql_changed", False) for d in diff),
                                    "answer_changed": sum(d.get("answer_changed", False) for d in diff)}
    s3.put_object(Bucket=OUT_BUCKET, Key="codebase_community/gold/reference_answers.json",
                  Body=json.dumps({"summary": summary, "diff": diff, "results": out}, default=str).encode(),
                  ContentType="application/json")
    log("written")
    flagged = [{"question_id": r["question_id"], "question": r["question"], "flag": f,
                "detail": (r.get("error") or r.get("tie") or "")}
               for r in out["corrected_20251106"]
               for f in (["error"] if not r["ok"] else []) + (["empty"] if r["ok"] and r["n_rows"] == 0 else []) +
                        (["tie"] if r.get("tie") and r["tie"].get("tied") else [])]
    return {"summary": summary, "diff": diff, "flagged_corrected": flagged}
