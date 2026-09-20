// Constraints and indexes for the codebase_community graph.
// Neo4j Community 2026.07.1, Cypher 25. The 7 node-key constraints are also created by
// etl/load_csv_from_s3.py BEFORE loading (relationship MATCHes need them); same names, so
// IF NOT EXISTS makes this script safe to run afterwards. Uniqueness is the only constraint type available in Community;
// each one creates a backing range index, so no separate index on these keys.

// --- Business keys -----------------------------------------------------------
CREATE CONSTRAINT user_userid_unique         IF NOT EXISTS FOR (n:User)        REQUIRE n.userId        IS UNIQUE;
CREATE CONSTRAINT post_postid_unique         IF NOT EXISTS FOR (n:Post)        REQUIRE n.postId        IS UNIQUE;
CREATE CONSTRAINT comment_commentid_unique      IF NOT EXISTS FOR (n:Comment)     REQUIRE n.commentId     IS UNIQUE;
CREATE CONSTRAINT vote_voteid_unique         IF NOT EXISTS FOR (n:Vote)        REQUIRE n.voteId        IS UNIQUE;
CREATE CONSTRAINT posthistory_posthistoryid_unique IF NOT EXISTS FOR (n:PostHistory) REQUIRE n.postHistoryId IS UNIQUE;
CREATE CONSTRAINT tag_tagid_unique          IF NOT EXISTS FOR (n:Tag)         REQUIRE n.tagId         IS UNIQUE;
CREATE CONSTRAINT tag_name_unique        IF NOT EXISTS FOR (n:Tag)         REQUIRE n.tagName       IS UNIQUE;
CREATE CONSTRAINT badge_name_unique      IF NOT EXISTS FOR (n:Badge)       REQUIRE n.name          IS UNIQUE;

// Relationship keys carried over from join/event tables.
CREATE CONSTRAINT links_to_id_unique IF NOT EXISTS FOR ()-[r:LINKS_TO]-() REQUIRE r.postLinkId IS UNIQUE;
CREATE CONSTRAINT earned_id_unique   IF NOT EXISTS FOR ()-[r:EARNED]-()   REQUIRE r.badgeId    IS UNIQUE;

// --- Range indexes: equality / range / STARTS WITH / IN -----------------------
CREATE INDEX user_display_name   IF NOT EXISTS FOR (n:User)    ON (n.displayName);
CREATE INDEX user_reputation     IF NOT EXISTS FOR (n:User)    ON (n.reputation);
CREATE INDEX user_location       IF NOT EXISTS FOR (n:User)    ON (n.location);
CREATE INDEX user_creation_date  IF NOT EXISTS FOR (n:User)    ON (n.creationDate);
CREATE INDEX post_title          IF NOT EXISTS FOR (n:Post)    ON (n.title);
CREATE INDEX post_score          IF NOT EXISTS FOR (n:Post)    ON (n.score);
CREATE INDEX post_view_count     IF NOT EXISTS FOR (n:Post)    ON (n.viewCount);
CREATE INDEX post_creation_date  IF NOT EXISTS FOR (n:Post)    ON (n.creationDate);
CREATE INDEX comment_created     IF NOT EXISTS FOR (n:Comment) ON (n.creationDate);
CREATE INDEX comment_score       IF NOT EXISTS FOR (n:Comment) ON (n.score);
CREATE INDEX vote_creation_date  IF NOT EXISTS FOR (n:Vote)    ON (n.creationDate);
CREATE INDEX vote_bounty_amount  IF NOT EXISTS FOR (n:Vote)    ON (n.bountyAmount);
CREATE INDEX earned_date         IF NOT EXISTS FOR ()-[r:EARNED]-()   ON (r.date);
CREATE INDEX links_to_created    IF NOT EXISTS FOR ()-[r:LINKS_TO]-() ON (r.creationDate);

// --- Text indexes: CONTAINS / ENDS WITH, and equality on long free text -------
// Measured maxima: Post.title 154 chars, Comment.text 667 chars. Index size limits still unconfirmed in docs.
CREATE TEXT INDEX post_title_text   IF NOT EXISTS FOR (n:Post)        ON (n.title);
CREATE TEXT INDEX comment_text_text IF NOT EXISTS FOR (n:Comment)     ON (n.text);
// PostHistory.text is NOT indexed: values reach 31k chars and total ~199M chars; one gold query filters on it.
// Revisit with PROFILE before adding.
