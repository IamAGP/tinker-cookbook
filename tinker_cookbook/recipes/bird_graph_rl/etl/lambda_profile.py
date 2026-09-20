"""One-off Lambda: profile the BIRD codebase_community SQLite file straight from S3.

Emits row counts, FK orphan counts, NULL rates, lookup-id distributions, tag-parse
coverage, datetime-format violations and text-size totals. Nothing is staged locally.
"""
import json
import os
import re
import sqlite3
import time

import boto3

SRC_BUCKET = os.environ["SRC_BUCKET"]
SRC_KEY = os.environ["SRC_KEY"]
OUT_BUCKET = os.environ["OUT_BUCKET"]
DB = "/tmp/db.sqlite"
T0 = time.time()

FKS = [
    ("badges", "UserId", "users"), ("comments", "PostId", "posts"), ("comments", "UserId", "users"),
    ("postHistory", "PostId", "posts"), ("postHistory", "UserId", "users"),
    ("postLinks", "PostId", "posts"), ("postLinks", "RelatedPostId", "posts"),
    ("posts", "OwnerUserId", "users"), ("posts", "LastEditorUserId", "users"),
    ("posts", "ParentId", "posts"), ("posts", "AcceptedAnswerId", "posts"),
    ("tags", "ExcerptPostId", "posts"), ("tags", "WikiPostId", "posts"),
    ("votes", "PostId", "posts"), ("votes", "UserId", "users"),
]
DATETIME_COLS = [
    ("badges", "Date"), ("comments", "CreationDate"), ("postHistory", "CreationDate"),
    ("postLinks", "CreationDate"), ("posts", "CreaionDate"), ("posts", "LasActivityDate"),
    ("posts", "LastEditDate"), ("posts", "CommunityOwnedDate"), ("posts", "ClosedDate"),
    ("users", "CreationDate"), ("users", "LastAccessDate"), ("votes", "CreationDate"),
]
TEXT_COLS = [("posts", "Body"), ("posts", "Title"), ("comments", "Text"),
             ("postHistory", "Text"), ("postHistory", "Comment"), ("users", "AboutMe")]
DISTS = [("posts", "PostTypeId"), ("votes", "VoteTypeId"),
         ("postHistory", "PostHistoryTypeId"), ("postLinks", "LinkTypeId")]


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def handler(event, context):
    s3 = boto3.client("s3")
    log(f"downloading s3://{SRC_BUCKET}/{SRC_KEY}")
    s3.download_file(SRC_BUCKET, SRC_KEY, DB)
    log(f"downloaded {os.path.getsize(DB)} bytes")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q = lambda sql: con.execute(sql).fetchall()
    out = {"file_bytes": os.path.getsize(DB), "sqlite_version": sqlite3.sqlite_version}

    tables = [r[0] for r in q("select name from sqlite_master where type='table' order by 1")]
    out["row_counts"] = {t: q(f'select count(*) from "{t}"')[0][0] for t in tables}
    log(f"row counts {out['row_counts']}")

    out["fk"] = {}
    for child, col, parent in FKS:
        nonnull = q(f'select count(*) from "{child}" where "{col}" is not null')[0][0]
        orphan = q(f'select count(*) from "{child}" c where c."{col}" is not null and not exists '
                   f'(select 1 from "{parent}" p where p.Id = c."{col}")')[0][0]
        out["fk"][f"{child}.{col}->{parent}"] = {"non_null": nonnull, "orphans": orphan}
        log(f"fk {child}.{col}: non_null={nonnull} orphans={orphan}")

    out["distributions"] = {f"{t}.{c}": dict(q(f'select "{c}", count(*) from "{t}" group by 1 order by 2 desc'))
                            for t, c in DISTS}
    log("distributions done")

    out["datetime_violations"] = {}
    for t, c in DATETIME_COLS:
        glob = "????-??-??" if (t, c) == ("votes", "CreationDate") else "????-??-?? ??:??:??*"
        bad = q(f'select count(*) from "{t}" where "{c}" is not null and "{c}" not glob \'{glob}\'')[0][0]
        frac = q(f'select count(*) from "{t}" where "{c}" like \'%.%\' and "{c}" not like \'%.0\'')[0][0]
        sample = q(f'select "{c}" from "{t}" where "{c}" is not null limit 2')
        out["datetime_violations"][f"{t}.{c}"] = {"bad_format": bad, "nonzero_fraction": frac,
                                                  "sample": [s[0] for s in sample]}
    log("datetime checks done")

    out["text"] = {}
    for t, c in TEXT_COLS:
        n, tot, mx = q(f'select count("{c}"), coalesce(sum(length("{c}")),0), coalesce(max(length("{c}")),0) from "{t}"')[0]
        out["text"][f"{t}.{c}"] = {"non_null": n, "total_chars": tot, "max_chars": mx}
    log("text sizes done")

    tag_ids = {name: tid for tid, name in q("select Id, TagName from tags")}
    used, unknown, posts_with_tags, pairs = {}, {}, 0, 0
    for (raw,) in con.execute("select Tags from posts where Tags is not null and Tags <> ''"):
        posts_with_tags += 1
        for name in re.findall(r"<([^<>]+)>", raw):
            pairs += 1
            used[name] = used.get(name, 0) + 1
            if name not in tag_ids:
                unknown[name] = unknown.get(name, 0) + 1
    declared = dict(q("select TagName, Count from tags"))
    mismatch = sum(1 for k, v in declared.items() if used.get(k, 0) != v)
    out["tags"] = {"tags_table_rows": len(tag_ids), "posts_with_tags": posts_with_tags,
                   "post_tag_pairs": pairs, "distinct_parsed": len(used),
                   "parsed_not_in_tags_table": len(unknown),
                   "unknown_examples": sorted(unknown.items(), key=lambda kv: -kv[1])[:10],
                   "tags_where_declared_count_differs_from_parsed": mismatch,
                   "tagname_duplicates": q("select count(*) from (select TagName from tags group by 1 having count(*)>1)")[0][0]}
    log(f"tags {out['tags']['post_tag_pairs']} pairs, unknown={len(unknown)}")

    out["misc"] = {
        "distinct_badge_names": q("select count(distinct Name) from badges")[0][0],
        "top_badges": q("select Name, count(*) from badges group by 1 order by 2 desc limit 5"),
        "distinct_display_names": q("select count(distinct DisplayName) from users")[0][0],
        "users_null_display_name": q("select count(*) from users where DisplayName is null")[0][0],
        "posts_null_owner_with_display_name": q("select count(*) from posts where OwnerUserId is null and OwnerDisplayName is not null")[0][0],
        "postlinks_duplicate_pairs": q("select count(*) from (select PostId, RelatedPostId, LinkTypeId from postLinks group by 1,2,3 having count(*)>1)")[0][0],
        "max_posts_per_user": q("select OwnerUserId, count(*) from posts where OwnerUserId is not null group by 1 order by 2 desc limit 3"),
        "max_posts_per_tag_declared": q("select TagName, Count from tags order by Count desc limit 3"),
        "answers_whose_parent_is_not_question": q("select count(*) from posts a join posts p on p.Id=a.ParentId where p.PostTypeId<>1")[0][0],
        "null_rates_users": {c: q(f'select count(*) from users where "{c}" is null')[0][0]
                             for c in ["Age", "Location", "WebsiteUrl", "AboutMe", "ProfileImageUrl"]},
        "empty_string_counts": {f"{t}.{c}": q(f'select count(*) from "{t}" where "{c}" = \'\'')[0][0]
                                for t, c in TEXT_COLS},
    }
    log("misc done")

    key = "codebase_community/profile.json"
    s3.put_object(Bucket=OUT_BUCKET, Key=key, Body=json.dumps(out, indent=1, default=str).encode(),
                  ContentType="application/json")
    log(f"wrote s3://{OUT_BUCKET}/{key}")
    return out
