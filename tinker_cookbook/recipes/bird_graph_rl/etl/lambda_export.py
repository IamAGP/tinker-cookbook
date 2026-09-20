"""One-off Lambda: export BIRD codebase_community (SQLite in S3) to neo4j-admin import CSVs in S3.

One CSV object per node label / relationship source, header on the first line, RFC 4180
quoting. Orphaned foreign keys are dropped from relationship files (the node is kept) and
counted in manifest.json, which is the reconciliation target after import.
"""
import csv
import json
import os
import re
import sqlite3
import time

import boto3

SRC_BUCKET = os.environ["SRC_BUCKET"]
SRC_KEY = os.environ["SRC_KEY"]
OUT_BUCKET = os.environ["OUT_BUCKET"]
PREFIX = "codebase_community/csv/"
DB = "/tmp/db.sqlite"
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def dt(col):
    """'2010-07-19 19:12:12.0' -> '2010-07-19T19:12:12' (profile: fraction is always .0)."""
    return f"replace(substr({col}, 1, 19), ' ', 'T')"


NODES = {
    "users": ("User", [":ID(User)", "userId:long", "displayName", "reputation:long",
                       "creationDate:localdatetime", "lastAccessDate:localdatetime", "websiteUrl",
                       "location", "aboutMe", "views:long", "upVotes:long", "downVotes:long",
                       "accountId:long", "age:long", "profileImageUrl"],
              f"select Id, Id, DisplayName, Reputation, {dt('CreationDate')}, {dt('LastAccessDate')}, "
              "WebsiteUrl, Location, AboutMe, Views, UpVotes, DownVotes, AccountId, Age, ProfileImageUrl from users"),
    "posts": (None, [":ID(Post)", ":LABEL", "postId:long", "postTypeId:long", "creationDate:localdatetime",
                     "score:long", "viewCount:long", "body", "lastActivityDate:localdatetime", "title",
                     "answerCount:long", "commentCount:long", "favoriteCount:long",
                     "lastEditDate:localdatetime", "communityOwnedDate:localdatetime",
                     "closedDate:localdatetime", "ownerDisplayName", "lastEditorDisplayName"],
              "select Id, case PostTypeId when 1 then 'Post;Question' when 2 then 'Post;Answer' else 'Post' end, "
              f"Id, PostTypeId, {dt('CreaionDate')}, Score, ViewCount, Body, {dt('LasActivityDate')}, Title, "
              f"AnswerCount, CommentCount, FavoriteCount, {dt('LastEditDate')}, {dt('CommunityOwnedDate')}, "
              f"{dt('ClosedDate')}, OwnerDisplayName, LastEditorDisplayName from posts"),
    "comments": ("Comment", [":ID(Comment)", "commentId:long", "score:long", "text",
                             "creationDate:localdatetime", "userDisplayName"],
                 f"select Id, Id, Score, Text, {dt('CreationDate')}, UserDisplayName from comments"),
    "votes": ("Vote", [":ID(Vote)", "voteId:long", "voteTypeId:long", "creationDate:date", "bountyAmount:long"],
              "select Id, Id, VoteTypeId, CreationDate, BountyAmount from votes"),
    "post_history": ("PostHistory", [":ID(PostHistory)", "postHistoryId:long", "postHistoryTypeId:long",
                                     "revisionGuid", "creationDate:localdatetime", "text", "comment",
                                     "userDisplayName"],
                     f"select Id, Id, PostHistoryTypeId, RevisionGUID, {dt('CreationDate')}, Text, Comment, "
                     "UserDisplayName from postHistory"),
    "tags": ("Tag", [":ID(Tag)", "tagId:long", "tagName", "count:long"],
             "select Id, Id, TagName, Count from tags"),
    "badges": ("Badge", [":ID(Badge)", "name"], "select distinct Name, Name from badges order by 1"),
}

# name -> (TYPE, header, sql). Every FK is inner-joined to its parent so orphans are excluded.
RELS = {
    "owns": ("OWNS", [":START_ID(User)", ":END_ID(Post)"],
             "select p.OwnerUserId, p.Id from posts p join users u on u.Id = p.OwnerUserId"),
    "last_edited": ("LAST_EDITED", [":START_ID(User)", ":END_ID(Post)"],
                    "select p.LastEditorUserId, p.Id from posts p join users u on u.Id = p.LastEditorUserId"),
    "answers": ("ANSWERS", [":START_ID(Post)", ":END_ID(Post)"],
                "select a.Id, a.ParentId from posts a join posts q on q.Id = a.ParentId"),
    "accepted": ("ACCEPTED", [":START_ID(Post)", ":END_ID(Post)"],
                 "select q.Id, q.AcceptedAnswerId from posts q join posts a on a.Id = q.AcceptedAnswerId"),
    "has_excerpt": ("HAS_EXCERPT", [":START_ID(Tag)", ":END_ID(Post)"],
                    "select t.Id, t.ExcerptPostId from tags t join posts p on p.Id = t.ExcerptPostId"),
    "has_wiki": ("HAS_WIKI", [":START_ID(Tag)", ":END_ID(Post)"],
                 "select t.Id, t.WikiPostId from tags t join posts p on p.Id = t.WikiPostId"),
    "links_to": ("LINKS_TO", [":START_ID(Post)", ":END_ID(Post)", "postLinkId:long", "linkTypeId:long",
                              "creationDate:localdatetime"],
                 f"select l.PostId, l.RelatedPostId, l.Id, l.LinkTypeId, {dt('l.CreationDate')} from postLinks l "
                 "join posts a on a.Id = l.PostId join posts b on b.Id = l.RelatedPostId"),
    "wrote": ("WROTE", [":START_ID(User)", ":END_ID(Comment)"],
              "select c.UserId, c.Id from comments c join users u on u.Id = c.UserId"),
    "comment_on_post": ("ON_POST", [":START_ID(Comment)", ":END_ID(Post)"],
                        "select c.Id, c.PostId from comments c join posts p on p.Id = c.PostId"),
    "cast": ("CAST", [":START_ID(User)", ":END_ID(Vote)"],
             "select v.UserId, v.Id from votes v join users u on u.Id = v.UserId"),
    "vote_on_post": ("ON_POST", [":START_ID(Vote)", ":END_ID(Post)"],
                     "select v.Id, v.PostId from votes v join posts p on p.Id = v.PostId"),
    "made": ("MADE", [":START_ID(User)", ":END_ID(PostHistory)"],
             "select h.UserId, h.Id from postHistory h join users u on u.Id = h.UserId"),
    "revises": ("REVISES", [":START_ID(PostHistory)", ":END_ID(Post)"],
                "select h.Id, h.PostId from postHistory h join posts p on p.Id = h.PostId"),
    "earned": ("EARNED", [":START_ID(User)", ":END_ID(Badge)", "badgeId:long", "date:localdatetime"],
               f"select b.UserId, b.Name, b.Id, {dt('b.Date')} from badges b join users u on u.Id = b.UserId"),
}


def write_and_upload(s3, name, header, rows):
    path = f"/tmp/{name}.csv"
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow(header)
        for row in rows:
            w.writerow(row)
            n += 1
    size = os.path.getsize(path)
    s3.upload_file(path, OUT_BUCKET, f"{PREFIX}{name}.csv")
    os.remove(path)
    log(f"{name}: rows={n} bytes={size} uploaded")
    return {"rows": n, "bytes": size}


def handler(event, context):
    s3 = boto3.client("s3")
    log("downloading source")
    s3.download_file(SRC_BUCKET, SRC_KEY, DB)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    manifest = {"nodes": {}, "relationships": {}}

    for name, (label, header, sql) in NODES.items():
        manifest["nodes"][name] = {"label": label or "from :LABEL column",
                                   **write_and_upload(s3, f"nodes_{name}", header, con.execute(sql))}

    for name, (rtype, header, sql) in RELS.items():
        manifest["relationships"][name] = {"type": rtype,
                                           **write_and_upload(s3, f"rels_{name}", header, con.execute(sql))}

    tag_ids = {n: i for i, n in con.execute("select Id, TagName from tags")}

    def tagged():
        for pid, raw in con.execute("select Id, Tags from posts where Tags is not null and Tags <> ''"):
            for t in dict.fromkeys(re.findall(r"<([^<>]+)>", raw)):  # de-dup within a post, keep order
                yield pid, tag_ids[t]

    manifest["relationships"]["tagged"] = {"type": "TAGGED", **write_and_upload(
        s3, "rels_tagged", [":START_ID(Post)", ":END_ID(Tag)"], tagged())}

    manifest["totals"] = {"nodes": sum(v["rows"] for v in manifest["nodes"].values()),
                          "relationships": sum(v["rows"] for v in manifest["relationships"].values()),
                          "bytes": sum(v["bytes"] for g in ("nodes", "relationships") for v in manifest[g].values())}
    s3.put_object(Bucket=OUT_BUCKET, Key="codebase_community/manifest.json",
                  Body=json.dumps(manifest, indent=1).encode(), ContentType="application/json")
    log(f"done {manifest['totals']}")
    return manifest
