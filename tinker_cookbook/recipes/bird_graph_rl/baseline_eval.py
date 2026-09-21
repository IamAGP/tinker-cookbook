"""Zero-shot baseline: can a model answer BIRD's questions by writing Cypher against the graph?

Scores the model's returned rows against reference answers obtained by executing BIRD's gold
SQL on the original SQLite file, so no gold Cypher is needed. Concurrent by design (the #1
performance mistake is sequential API calls).

Reads reference answers from object storage; writes results incrementally to log_path so a
killed run keeps everything finished so far.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any

import chz
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

SYSTEM = """You answer questions about a Stack Exchange community by querying a Neo4j graph.

Schema:
(:User {userId, displayName, reputation, creationDate, lastAccessDate, websiteUrl, location, aboutMe, views, upVotes, downVotes, accountId, age, profileImageUrl})
(:Post:Question|:Answer {postId, postTypeId, creationDate, score, viewCount, body, title, lastActivityDate, lastEditDate, communityOwnedDate, closedDate, answerCount, commentCount, favoriteCount, ownerDisplayName, lastEditorDisplayName})
(:Comment {commentId, score, text, creationDate, userDisplayName})
(:Vote {voteId, voteTypeId, creationDate, bountyAmount})
(:PostHistory {postHistoryId, postHistoryTypeId, revisionGuid, creationDate, text, comment, userDisplayName})
(:Tag {tagId, tagName, count})
(:Badge {name})

Relationships:
(User)-[:OWNS]->(Post)                 the post's author
(User)-[:LAST_EDITED]->(Post)
(Answer)-[:ANSWERS]->(Question)
(Question)-[:ACCEPTED]->(Answer)
(Post)-[:TAGGED]->(Tag)
(Tag)-[:HAS_EXCERPT|:HAS_WIKI]->(Post)
(Post)-[:LINKS_TO {postLinkId, linkTypeId, creationDate}]->(Post)
(User)-[:WROTE]->(Comment)-[:ON_POST]->(Post)
(User)-[:CAST]->(Vote)-[:ON_POST]->(Post)
(User)-[:MADE]->(PostHistory)-[:REVISES]->(Post)
(User)-[:EARNED {badgeId, date}]->(Badge)

Notes:
- Dates are temporal values. Filter a year with `p.creationDate.year = 2010`.
- NULLs are absent, not stored.
- Counter properties (answerCount, commentCount, favoriteCount, Tag.count, User.upVotes) are
  stored snapshots; prefer them over counting relationships when the question asks for them.
- "posts by X" means (User)-[:OWNS]->(Post).
- displayName is not unique.

Call the run_cypher tool to execute a read-only query. You may call it more than once.
When you have the answer, reply with the final answer only, no explanation."""

TOOL = {"type": "function", "function": {
    "name": "run_cypher", "description": "Execute a read-only Cypher query and return rows.",
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}


class CypherTool:
    """Read-only Cypher access. Read transactions only; the server has no RBAC."""

    def __init__(self, uri: str, user: str, password: str, row_cap: int = 50):
        self._driver = GraphDatabase.driver(uri, auth=(user, password), notifications_min_severity="OFF")
        self._row_cap = row_cap

    def run(self, query: str) -> dict[str, Any]:
        if re.search(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|CALL\s+\{[^}]*\bSET\b)\b", query, re.I):
            return {"error": "write operations are not allowed"}
        try:
            with self._driver.session() as s:
                res = s.execute_read(lambda tx: [r.values() for r in tx.run(query)])
            return {"n_rows": len(res), "rows": [[str(v) for v in row] for row in res[: self._row_cap]],
                    "truncated": len(res) > self._row_cap}
        except Exception as e:  # noqa: BLE001 - the model needs to see the failure text
            return {"error": f"{type(e).__name__}: {str(e)[:300]}"}

    def close(self) -> None:
        self._driver.close()


def _norm(v: Any) -> str:
    """Compare loosely: numbers to 3dp, strings case-folded and stripped."""
    s = str(v).strip()
    if s.lower() in ("none", "null", ""):
        return ""
    try:
        return f"{round(float(s), 3):g}"
    except ValueError:
        return s.casefold()


def score(model_rows: list[list[str]], reference_rows: list[list[Any]]) -> dict[str, Any]:
    """Set-equality on normalised values, plus a looser 'contains every reference value' signal."""
    ref_flat = {_norm(v) for row in reference_rows for v in row} - {""}
    got_flat = {_norm(v) for row in model_rows for v in row} - {""}
    ref_set = {tuple(_norm(v) for v in row) for row in reference_rows}
    got_set = {tuple(_norm(v) for v in row) for row in model_rows}
    return {"exact_rows": ref_set == got_set,
            "values_match": ref_flat == got_flat,
            "reference_covered": bool(ref_flat) and ref_flat <= got_flat,
            "n_reference_rows": len(reference_rows), "n_model_rows": len(model_rows)}


@chz.chz
class Config:
    model_name: str = "Qwen/Qwen3.5-9B"
    reference_uri: str = ""          # s3://bucket/key of reference_answers.json
    gold_set: str = "corrected_20251106"
    log_path: str = ""
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    max_turns: int = 6
    max_tokens: int = 1024
    concurrency: int = 16
    limit: int | None = None         # smoke-test on the first N questions
    row_cap: int = 50


async def run_one(cfg: Config, sampling_client, renderer, tool: CypherTool, item: dict) -> dict:
    """One question: let the model query the graph for up to max_turns, then score its answer."""
    from tinker_cookbook import renderers

    convo = [renderers.Message(role="system", content=SYSTEM),
             renderers.Message(role="user", content=_question_text(item))]
    transcript, t0 = [], time.time()
    for _ in range(cfg.max_turns):
        model_input = renderer.build_generation_prompt(convo)
        out = await sampling_client.sample_async(
            prompt=model_input, num_samples=1,
            sampling_params=__import__("tinker").types.SamplingParams(
                max_tokens=cfg.max_tokens, temperature=0.0, stop=renderer.get_stop_sequences()))
        message, _ = renderer.parse_response(out.sequences[0].tokens)
        convo.append(message)
        calls = _tool_calls(message)
        if not calls:
            break
        for q in calls:
            result = await asyncio.to_thread(tool.run, q)
            transcript.append({"query": q, "result": result})
            convo.append(renderers.Message(role="user", content=f"Result: {json.dumps(result)[:4000]}"))
    answer_rows = [r["result"].get("rows", []) for r in transcript if "rows" in r.get("result", {})]
    last_rows = answer_rows[-1] if answer_rows else []
    return {"question_id": item["question_id"], "question": item["question"],
            "difficulty": item.get("difficulty"), "n_queries": len(transcript),
            "final_text": convo[-1].content if convo else "", "transcript": transcript,
            "seconds": round(time.time() - t0, 1),
            **score(last_rows, item.get("rows", []))}


def _question_text(item: dict) -> str:
    ev = (item.get("evidence") or "").strip()
    return f"{item['question']}\n\nHint: {ev}" if ev else item["question"]


def _tool_calls(message) -> list[str]:
    """Accept either native tool calls or a ```cypher fenced block."""
    for tc in (getattr(message, "tool_calls", None) or []):
        try:
            args = tc.function.arguments
            yielded = json.loads(args) if isinstance(args, str) else args
            if q := yielded.get("query"):
                return [q]
        except Exception:  # noqa: BLE001
            pass
    blocks = re.findall(r"```(?:cypher)?\s*(MATCH\b.*?)```", message.content or "", re.S | re.I)
    return [b.strip() for b in blocks[:1]]
