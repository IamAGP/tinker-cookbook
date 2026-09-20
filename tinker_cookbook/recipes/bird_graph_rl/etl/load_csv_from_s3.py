"""Stream the exported CSVs from S3 into a local Neo4j via LOAD CSV over presigned HTTPS URLs.

Why not `neo4j-admin database import`: Community Edition ships no S3 storage provider
("No storage system found for scheme: s3"), and the dataset must not be staged on disk.
LOAD CSV reads the HTTPS stream directly, so nothing but the Neo4j store touches the laptop.

Requires `db.import.csv.legacy_quote_escaping=false` (RFC 4180), otherwise backslashes in
post bodies (LaTeX) corrupt quoted fields.

Env: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, CSV_BUCKET, CSV_PREFIX, AWS_REGION.
"""
import logging
import os
import sys
import time

import boto3
from botocore.config import Config
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("load")

BATCH = 5000
KEY_CONSTRAINTS = {  # created BEFORE the load: relationship MATCHes depend on these indexes
    "User": "userId", "Post": "postId", "Comment": "commentId", "Vote": "voteId",
    "PostHistory": "postHistoryId", "Tag": "tagId", "Badge": "name",
}
INT, LDT, DATE, STR = "toInteger", "localdatetime", "date", ""

# file -> (label expression, {property: (csv column, converter)})
NODES = {
    "nodes_users": ("User", {
        "userId": ("userId:long", INT), "displayName": ("displayName", STR),
        "reputation": ("reputation:long", INT), "creationDate": ("creationDate:localdatetime", LDT),
        "lastAccessDate": ("lastAccessDate:localdatetime", LDT), "websiteUrl": ("websiteUrl", STR),
        "location": ("location", STR), "aboutMe": ("aboutMe", STR), "views": ("views:long", INT),
        "upVotes": ("upVotes:long", INT), "downVotes": ("downVotes:long", INT),
        "accountId": ("accountId:long", INT), "age": ("age:long", INT),
        "profileImageUrl": ("profileImageUrl", STR)}),
    "nodes_posts": ("$(split(row.`:LABEL`, ';'))", {
        "postId": ("postId:long", INT), "postTypeId": ("postTypeId:long", INT),
        "creationDate": ("creationDate:localdatetime", LDT), "score": ("score:long", INT),
        "viewCount": ("viewCount:long", INT), "body": ("body", STR),
        "lastActivityDate": ("lastActivityDate:localdatetime", LDT), "title": ("title", STR),
        "answerCount": ("answerCount:long", INT), "commentCount": ("commentCount:long", INT),
        "favoriteCount": ("favoriteCount:long", INT), "lastEditDate": ("lastEditDate:localdatetime", LDT),
        "communityOwnedDate": ("communityOwnedDate:localdatetime", LDT),
        "closedDate": ("closedDate:localdatetime", LDT), "ownerDisplayName": ("ownerDisplayName", STR),
        "lastEditorDisplayName": ("lastEditorDisplayName", STR)}),
    "nodes_comments": ("Comment", {
        "commentId": ("commentId:long", INT), "score": ("score:long", INT), "text": ("text", STR),
        "creationDate": ("creationDate:localdatetime", LDT), "userDisplayName": ("userDisplayName", STR)}),
    "nodes_votes": ("Vote", {
        "voteId": ("voteId:long", INT), "voteTypeId": ("voteTypeId:long", INT),
        "creationDate": ("creationDate:date", DATE), "bountyAmount": ("bountyAmount:long", INT)}),
    "nodes_post_history": ("PostHistory", {
        "postHistoryId": ("postHistoryId:long", INT), "postHistoryTypeId": ("postHistoryTypeId:long", INT),
        "revisionGuid": ("revisionGuid", STR), "creationDate": ("creationDate:localdatetime", LDT),
        "text": ("text", STR), "comment": ("comment", STR), "userDisplayName": ("userDisplayName", STR)}),
    "nodes_tags": ("Tag", {"tagId": ("tagId:long", INT), "tagName": ("tagName", STR),
                           "count": ("count:long", INT)}),
    "nodes_badges": ("Badge", {"name": ("name", STR)}),
}

# file -> (TYPE, (start label, key, is_int), (end label, key, is_int), {rel property: (column, conv)})
U, P, C, V, H, T, B = (("User", "userId", True), ("Post", "postId", True), ("Comment", "commentId", True),
                       ("Vote", "voteId", True), ("PostHistory", "postHistoryId", True),
                       ("Tag", "tagId", True), ("Badge", "name", False))
RELS = {
    "rels_owns": ("OWNS", U, P, {}), "rels_last_edited": ("LAST_EDITED", U, P, {}),
    "rels_answers": ("ANSWERS", P, P, {}), "rels_accepted": ("ACCEPTED", P, P, {}),
    "rels_has_excerpt": ("HAS_EXCERPT", T, P, {}), "rels_has_wiki": ("HAS_WIKI", T, P, {}),
    "rels_links_to": ("LINKS_TO", P, P, {"postLinkId": ("postLinkId:long", INT),
                                         "linkTypeId": ("linkTypeId:long", INT),
                                         "creationDate": ("creationDate:localdatetime", LDT)}),
    "rels_wrote": ("WROTE", U, C, {}), "rels_comment_on_post": ("ON_POST", C, P, {}),
    "rels_cast": ("CAST", U, V, {}), "rels_vote_on_post": ("ON_POST", V, P, {}),
    "rels_made": ("MADE", U, H, {}), "rels_revises": ("REVISES", H, P, {}),
    "rels_earned": ("EARNED", U, B, {"badgeId": ("badgeId:long", INT), "date": ("date:localdatetime", LDT)}),
    "rels_tagged": ("TAGGED", P, T, {}),
}


def prop_map(props):
    return ", ".join(f"{p}: {conv}(row.`{col}`)" if conv else f"{p}: row.`{col}`"
                     for p, (col, conv) in props.items())


def node_query(label, props):
    lab = label if label.startswith("$") else label
    return (f"LOAD CSV WITH HEADERS FROM $url AS row CALL (row) {{ CREATE (n:{lab}) SET n += {{{prop_map(props)}}} }} "
            f"IN TRANSACTIONS OF {BATCH} ROWS")


def rel_query(rtype, start, end, props):
    def ref(side, spec):
        label, key, is_int = spec
        col = f"row.`:{side}({label})`"
        return f"{{{key}: {'toInteger(' + col + ')' if is_int else col}}}"
    setp = f" SET r += {{{prop_map(props)}}}" if props else ""
    return (f"LOAD CSV WITH HEADERS FROM $url AS row CALL (row) {{ "
            f"MATCH (a:{start[0]} {ref('START_ID', start)}) MATCH (b:{end[0]} {ref('END_ID', end)}) "
            f"CREATE (a)-[r:{rtype}]->(b){setp} }} IN TRANSACTIONS OF {BATCH} ROWS")


def main():
    bucket, prefix = os.environ["CSV_BUCKET"], os.environ["CSV_PREFIX"]
    region = os.environ.get("AWS_REGION", "ap-south-1")
    # Regional endpoint on purpose: the global endpoint answers 307 for a recently created
    # regional bucket, and LOAD CSV does not follow that redirect.
    s3 = boto3.client("s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com",
                      config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    driver = GraphDatabase.driver(os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
                                  auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]))
    only = set(sys.argv[1:])
    with driver.session() as s:
        if not only:
            n = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            if n:
                sys.exit(f"refusing to load: database already holds {n} nodes (loader uses CREATE)")
        for label, key in KEY_CONSTRAINTS.items():
            s.run(f"CREATE CONSTRAINT {label.lower()}_{key.lower()}_unique IF NOT EXISTS "
                  f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE").consume()
        s.run("CALL db.awaitIndexes(120)").consume()
        log.info("key constraints online")
        t_all = time.time()
        jobs = [(f, node_query(*spec)) for f, spec in NODES.items()] + \
               [(f, rel_query(*spec)) for f, spec in RELS.items()]
        for fname, query in jobs:
            if only and fname not in only:
                continue
            url = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": f"{prefix}{fname}.csv"},
                                            ExpiresIn=3600)
            t = time.time()
            c = s.run(query, url=url).consume().counters
            log.info("%-22s nodes+%-7d rels+%-7d props+%-8d %.1fs", fname, c.nodes_created,
                     c.relationships_created, c.properties_set, time.time() - t)
        log.info("ALL DONE in %.1fs", time.time() - t_all)


if __name__ == "__main__":
    main()
