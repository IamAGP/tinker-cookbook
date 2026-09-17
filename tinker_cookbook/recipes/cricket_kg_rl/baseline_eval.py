"""Baseline harness for the cricket Cypher agent — the headroom + SFT-or-not test.

Runs a candidate (small) model ZERO-SHOT as an agent: it gets the schema + a
`run_cypher` tool wired to the live AuraDB graph, reasons, queries, and answers.
We score the final answer against execution-verified gold (entity + number match)
and break accuracy down BY DIFFICULTY — which tells us:

  - does the small base already tool-call Cypher? (if it can't → SFT cold-start)
  - where is the headroom? (which difficulty tiers it fails → where RL can help)

Mirrors the proven legal_rl/evaluate.py pattern. Single-process eval.

Gold pairs JSONL, one per line:
  {"id","question","difficulty","type","gold_cypher","gold_answer","entities":[...],"numbers":[...]}

Run:
  python -m tinker_cookbook.recipes.cricket_kg_rl.baseline_eval \
      base_model=Qwen/Qwen3.5-9B gold_path=<her_batch.jsonl>

Required: TINKER_API_KEY. Neo4j creds read from the AuraDB creds file (not the repo).
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from typing import Annotated

import chz
import tinker
from dotenv import dotenv_values
from neo4j import AsyncGraphDatabase

from tinker_cookbook import model_info, tokenizer_utils
from tinker_cookbook.completers import TinkerTokenCompleter
from tinker_cookbook.renderers import get_renderer, get_text_content
from tinker_cookbook.renderers.base import Message
from tinker_cookbook.rl.rollouts import do_single_rollout
from tinker_cookbook.tool_use import ToolResult, build_agent_tool_env, simple_tool_result, tool
from tinker_cookbook.tool_use.tools import error_tool_result

# Aura creds live OUTSIDE the public repo; read directly, never copied in.
CREDS_FILE = "/Users/adithyagiridharan/Desktop/PythonProjects/cricket-analytics/Neo4j-023e8664-Created-2026-06-24.txt"

MAX_ROWS = 30
MAX_RESULT_CHARS = 3000

# Concise schema (from the live get_neo4j_schema) embedded so the agent has it upfront.
SCHEMA = """CRICKET IPL KNOWLEDGE GRAPH SCHEMA (Neo4j).
Player names use cricinfo initials, e.g. "V Kohli", "JJ Bumrah", "CH Gayle".

NODES (key properties):
  Player(name)  Team(name)  Venue(name, city)  Tournament(name, season)  Official(name)
  Match(matchId, date, season, city, venue, overs, ballsPerOver)
  Innings(inningsNumber, targetRuns)
  Over(overNumber, runsScored, wickets)
  Delivery(ballNumber, batterRuns, totalRuns, extraRuns, extraType, isWicket, wides, noballs, byes, legbyes)
  Wicket(dismissalKind)
  BattingPerformance(runsScored, ballsFaced, strikeRate, fours, sixes, isOut)
  BowlingPerformance(runsConceded, wicketsTaken, economy, oversBowled, dotBalls)

RELATIONSHIPS:
  (Player)-[:FACED]->(Delivery)<-[:BOWLED]-(Player)        // batter faced ball the bowler bowled (head-to-head)
  (Player)-[:NON_STRIKER]->(Delivery)
  (Player)-[:BATTING_PERFORMANCE]->(BattingPerformance)-[:PERFORMANCE_IN_INNINGS]->(Innings)
  (Player)-[:BOWLING_PERFORMANCE]->(BowlingPerformance)-[:BOWLING_IN_INNINGS]->(Innings)
  (Innings)-[:HAS_OVER]->(Over)-[:HAS_DELIVERY]->(Delivery)
  (Match)-[:HAS_INNINGS]->(Innings)     (Match)-[:PLAYED_AT]->(Venue)
  (Team)-[:WON_MATCH {margin,marginType}]->(Match)   (Team)-[:WON_TOSS {decision}]->(Match)
  (Team)-[:PARTICIPATED_IN]->(Match)    (Team)-[:BATTED_IN]->(Innings)
  (Player)-[:PLAYER_OF_MATCH]->(Match)  (Player)-[:SQUAD_MEMBER {season}]->(Team)
  (Delivery)-[:RESULTED_IN_WICKET]->(Wicket)
  (Player)-[:DISMISSED]->(Wicket)  (Player)-[:BOWLER_TOOK_WICKET]->(Wicket)  (Player)-[:FIELDER_INVOLVED]->(Wicket)
"""

SYSTEM_PROMPT = (
    "You are a cricket analytics agent with a `run_cypher` tool over a Neo4j IPL graph.\n\n"
    + SCHEMA
    + "\nInstructions:\n"
    "1. Think step by step about what the question needs.\n"
    "2. Call run_cypher with a read-only Cypher query.\n"
    "3. Inspect the rows. Query again if needed.\n"
    "4. When you have the answer, stop calling tools and reply with the final answer in plain "
    "text, including the key number(s) and name(s).\n"
)

# 3 execution-verified fixtures so the harness runs before her batch lands.
FIXTURES: list[dict] = [
    {"id": "ex_easy_01", "difficulty": "easy", "type": "player_aggregate",
     "question": "How many sixes has CH Gayle hit in the IPL?",
     "gold_answer": 359, "entities": ["CH Gayle"], "numbers": [359]},
    {"id": "ex_med_01", "difficulty": "medium", "type": "player_extremum",
     "question": "What is V Kohli's highest score in a single IPL innings?",
     "gold_answer": 113, "entities": ["V Kohli"], "numbers": [113]},
    {"id": "ex_hard_01", "difficulty": "hard", "type": "head_to_head",
     "question": "How many runs has V Kohli scored off JJ Bumrah, and how many times has "
                 "Bumrah dismissed him?",
     "gold_answer": {"balls": 104, "runs": 155, "dismissals": 5},
     "entities": ["V Kohli", "JJ Bumrah"], "numbers": [104, 155, 5]},
]


class CypherTool:
    """run_cypher over AuraDB (async driver). Read-only guarded.

    Pickle-safe: the async driver is not picklable, so __getstate__ drops it and
    _ensure() lazily reconnects from the creds file (needed if RL shards the
    EnvGroupBuilder across processes).
    """

    def __init__(self, creds_file: str):
        self._creds_file = creds_file
        self._driver = None
        self._db = "neo4j"

    def __getstate__(self) -> dict:
        s = self.__dict__.copy()
        s["_driver"] = None
        return s

    def _ensure(self):
        if self._driver is None:
            c = dotenv_values(self._creds_file)
            self._driver = AsyncGraphDatabase.driver(
                c["NEO4J_URI"], auth=(c["NEO4J_USERNAME"], c["NEO4J_PASSWORD"])
            )
            self._db = c.get("NEO4J_DATABASE", "neo4j")
        return self._driver

    @tool
    async def run_cypher(
        self,
        query: Annotated[str, "A read-only Cypher query against the cricket IPL graph"],
    ) -> ToolResult:
        """Execute a read-only Cypher query and return the result rows as JSON."""
        up = query.strip().upper()
        for kw in ("CREATE", "MERGE", "DELETE", "SET ", "REMOVE", "DROP"):
            if re.search(rf"\b{kw.strip()}\b", up):
                return error_tool_result("Only read queries allowed.", name="run_cypher",
                                         error_type="write_blocked")
        try:
            drv = self._ensure()
            async with drv.session(database=self._db) as s:
                res = await s.run(query)
                rows = await res.data()
            rows = rows[:MAX_ROWS]
            text = json.dumps(rows, default=str, ensure_ascii=False)
            if len(text) > MAX_RESULT_CHARS:
                text = text[:MAX_RESULT_CHARS] + "... [truncated]"
            return simple_tool_result(text, name="run_cypher",
                                      metrics={"rows_returned": float(len(rows))})
        except Exception as e:
            return error_tool_result(str(e), name="run_cypher", error_type="cypher_error")


def _used_cypher(history: list[Message]) -> bool:
    for m in history:
        for tc in (m.get("tool_calls") or []):
            if tc.function.name == "run_cypher":
                return True
    return False


def score(history: list[Message], gold: dict) -> dict:
    """Structured scorer: needs a real query, then entity + number match vs gold."""
    final = ""
    for m in reversed(history):
        if m.get("role") == "assistant":
            final = get_text_content(m)
            break
    used_db = _used_cypher(history)
    if not used_db:
        return {"correct": 0.0, "entity": 0.0, "number": 0.0, "number_frac": 0.0, "no_query": 1.0}
    fa = final.lower()
    ents = [str(e).lower() for e in gold.get("entities", [])]
    nums = [str(n) for n in gold.get("numbers", [])]
    entity_match = all(e in fa for e in ents) if ents else 1.0
    # number present as a token (avoid 5 matching 155): word-ish boundary on digits
    def num_in(n: str) -> bool:
        return re.search(rf"(?<!\d){re.escape(n)}(?!\d)", fa) is not None
    n_hits = sum(num_in(n) for n in nums)
    number_match = (n_hits == len(nums)) if nums else True
    number_frac = (n_hits / len(nums)) if nums else 1.0   # dense signal for training
    correct = 1.0 if (entity_match and number_match) else 0.0
    return {"correct": correct, "entity": float(entity_match),
            "number": float(number_match), "number_frac": float(number_frac),
            "no_query": 0.0}


@chz.chz
class CLIConfig:
    base_model: str = "Qwen/Qwen3.5-9B"
    model_path: str | None = None
    gold_path: str | None = None   # JSONL; None → use FIXTURES
    max_turns: int = 6
    max_tokens: int = 1024
    max_trajectory_tokens: int = 32 * 1024
    concurrency: int = 6
    limit: int = 0   # 0 = all
    log_every: int = 10   # print running progress every N completed questions
    by_type: bool = False   # also print a per-question-type table (use for OOD held-out gate)


async def cli_main(config: CLIConfig) -> None:
    if config.gold_path:
        data = [json.loads(l) for l in open(config.gold_path) if l.strip()]
    else:
        data = FIXTURES
    if config.limit:
        data = data[: config.limit]
    label = config.model_path or f"{config.base_model} (base)"
    print(f"Baseline: {len(data)} questions | model: {label}")

    svc = tinker.ServiceClient()
    sc = (svc.create_sampling_client(model_path=config.model_path) if config.model_path
          else svc.create_sampling_client(base_model=config.base_model))
    policy = TinkerTokenCompleter(sc, max_tokens=config.max_tokens)
    tok = tokenizer_utils.get_tokenizer(config.base_model)
    renderer = get_renderer(model_info.get_recommended_renderer_name(config.base_model), tok)

    ctool = CypherTool(CREDS_FILE)
    sem = asyncio.Semaphore(config.concurrency)

    async def run_one(gold: dict) -> dict:
        msgs = renderer.create_conversation_prefix_with_tools(
            tools=[ctool.run_cypher.to_spec()], system_prompt=SYSTEM_PROMPT
        ) + [{"role": "user", "content": gold["question"]}]

        async def reward_fn(history):
            s = score(history, gold)
            return s["correct"], s
        env = build_agent_tool_env(
            renderer=renderer, tools=[ctool.run_cypher], initial_messages=msgs,
            reward_fn=reward_fn, max_turns=config.max_turns,
            max_trajectory_tokens=config.max_trajectory_tokens,
        )
        async with sem:
            traj = await do_single_rollout(policy, env)
        m = traj.transitions[-1].metrics if traj.transitions else {}
        return {"difficulty": gold.get("difficulty", "?"), "type": gold.get("type", "?"), **m,
                "turns": len(traj.transitions)}

    # Run with live progress (every `log_every` completions) instead of a
    # single end-print — so the run is observable, not a black box.
    tasks = [asyncio.create_task(run_one(g)) for g in data]
    results: list[dict] = []
    total = len(tasks)
    for fut in asyncio.as_completed(tasks):
        results.append(await fut)
        done = len(results)
        if done % config.log_every == 0 or done == total:
            rc = sum(x.get("correct", 0) for x in results) / done
            nq = sum(x.get("no_query", 0) for x in results) / done
            print(f"  progress {done}/{total} · running correct={rc:.3f} no_query={nq:.3f}",
                  flush=True)

    # Aggregate overall + by difficulty
    by_diff = defaultdict(list)
    for r in results:
        by_diff[r["difficulty"]].append(r)
    n = len(results)

    def agg(rows, key):
        return sum(r.get(key, 0) for r in rows) / len(rows) if rows else 0.0

    print("\n" + "=" * 78)
    print(f"BASELINE HEADROOM MAP — {label}")
    print("=" * 78)
    print(f"{'tier':<10}{'n':>4}{'correct':>10}{'entity':>9}{'number':>9}{'no_query':>10}{'turns':>7}")
    for tier in ["easy", "medium", "hard", "?"]:
        rows = by_diff.get(tier)
        if not rows:
            continue
        print(f"{tier:<10}{len(rows):>4}{agg(rows,'correct'):>10.3f}{agg(rows,'entity'):>9.3f}"
              f"{agg(rows,'number'):>9.3f}{agg(rows,'no_query'):>10.3f}{agg(rows,'turns'):>7.2f}")
    print("-" * 78)
    print(f"{'ALL':<10}{n:>4}{agg(results,'correct'):>10.3f}{agg(results,'entity'):>9.3f}"
          f"{agg(results,'number'):>9.3f}{agg(results,'no_query'):>10.3f}{agg(results,'turns'):>7.2f}")
    print("=" * 78)

    # Per-type breakdown (key for OOD held-out types: which patterns generalize)
    if config.by_type:
        by_type = defaultdict(list)
        for r in results:
            by_type[r["type"]].append(r)
        print(f"\n{'type':<24}{'n':>4}{'correct':>10}{'entity':>9}{'number':>9}{'no_query':>10}{'turns':>7}")
        for typ in sorted(by_type):
            rows = by_type[typ]
            print(f"{typ:<24}{len(rows):>4}{agg(rows,'correct'):>10.3f}{agg(rows,'entity'):>9.3f}"
                  f"{agg(rows,'number'):>9.3f}{agg(rows,'no_query'):>10.3f}{agg(rows,'turns'):>7.2f}")
        print("=" * 78)

    print("Read: no_query>0 → model isn't using the tool (cold-start → SFT needed).")
    print("      high correct on easy, low on hard → headroom is in hard tiers (RL target).")


if __name__ == "__main__":
    asyncio.run(cli_main(chz.entrypoint(CLIConfig)))
