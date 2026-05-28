"""
Auto-generate (question, answer, cypher) triples from the T20 cricket KG.

Each triple becomes one RL training episode:
  - question  → prompt given to the agent
  - answer    → ground truth used only by the reward function (never shown to model)
  - cypher    → reference query (for debugging only, not used in training)

Output: output/questions_<timestamp>.json

Usage:
    uv run python -m tinker_cookbook.recipes.cricket_kg_rl.generate_questions
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

load_dotenv()

OUTPUT_DIR = Path(__file__).parent / "output"

# Minimum overs bowled to qualify for economy / wicket rate questions
MIN_OVERS_BOWLED = 10.0
# Minimum runs scored to qualify for strike rate questions
MIN_RUNS_FOR_SR = 100


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class QAPair:
    question: str
    answer: str
    category: str
    season: int | None
    cypher: str  # reference only — not used during training


# ---------------------------------------------------------------------------
# Neo4j connection
# ---------------------------------------------------------------------------

def get_driver():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    if not uri or not password:
        print("ERROR: NEO4J_URI and NEO4J_PASSWORD must be set in .env")
        sys.exit(1)
    return GraphDatabase.driver(uri, auth=(user, password))


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def fetch_seasons(session) -> list[int]:
    result = session.run("MATCH (m:Match) RETURN DISTINCT m.season AS s ORDER BY s")
    return [r["s"] for r in result]


def fetch_teams(session) -> list[str]:
    result = session.run("MATCH (t:Team) RETURN t.name AS name ORDER BY name")
    return [r["name"] for r in result]


def fetch_players(session) -> list[str]:
    result = session.run("MATCH (p:Player) RETURN p.name AS name ORDER BY name")
    return [r["name"] for r in result]


# ---------------------------------------------------------------------------
# Template functions — each returns a QAPair or None if no data found
# ---------------------------------------------------------------------------

def q_top_run_scorer(session, season: int) -> QAPair | None:
    cypher = """
        MATCH (p:Player)-[:BATTING_PERFORMANCE]->(bp:BattingPerformance)
              -[:PERFORMANCE_IN_INNINGS]->(i:Innings)<-[:HAS_INNINGS]-(m:Match)
        WHERE m.season = $season
        WITH p.name AS player, sum(bp.runsScored) AS total
        ORDER BY total DESC LIMIT 1
        RETURN player, total
    """
    row = session.run(cypher, season=season).single()
    if not row:
        return None
    return QAPair(
        question=f"Who scored the most runs in IPL {season}?",
        answer=f"{row['player']} with {row['total']} runs",
        category="batting_season_stat",
        season=season,
        cypher=cypher.strip(),
    )


def q_top_wicket_taker(session, season: int) -> QAPair | None:
    cypher = """
        MATCH (p:Player)-[:BOWLING_PERFORMANCE]->(bp:BowlingPerformance)
              -[:BOWLING_IN_INNINGS]->(i:Innings)<-[:HAS_INNINGS]-(m:Match)
        WHERE m.season = $season
        WITH p.name AS player, sum(bp.wicketsTaken) AS total
        ORDER BY total DESC LIMIT 1
        RETURN player, total
    """
    row = session.run(cypher, season=season).single()
    if not row:
        return None
    return QAPair(
        question=f"Who took the most wickets in IPL {season}?",
        answer=f"{row['player']} with {row['total']} wickets",
        category="bowling_season_stat",
        season=season,
        cypher=cypher.strip(),
    )


def q_most_sixes(session, season: int) -> QAPair | None:
    cypher = """
        MATCH (p:Player)-[:BATTING_PERFORMANCE]->(bp:BattingPerformance)
              -[:PERFORMANCE_IN_INNINGS]->(i:Innings)<-[:HAS_INNINGS]-(m:Match)
        WHERE m.season = $season
        WITH p.name AS player, sum(bp.sixes) AS total
        ORDER BY total DESC LIMIT 1
        RETURN player, total
    """
    row = session.run(cypher, season=season).single()
    if not row:
        return None
    return QAPair(
        question=f"Which player hit the most sixes in IPL {season}?",
        answer=f"{row['player']} with {row['total']} sixes",
        category="batting_season_stat",
        season=season,
        cypher=cypher.strip(),
    )


def q_most_fours(session, season: int) -> QAPair | None:
    cypher = """
        MATCH (p:Player)-[:BATTING_PERFORMANCE]->(bp:BattingPerformance)
              -[:PERFORMANCE_IN_INNINGS]->(i:Innings)<-[:HAS_INNINGS]-(m:Match)
        WHERE m.season = $season
        WITH p.name AS player, sum(bp.fours) AS total
        ORDER BY total DESC LIMIT 1
        RETURN player, total
    """
    row = session.run(cypher, season=season).single()
    if not row:
        return None
    return QAPair(
        question=f"Which player hit the most fours in IPL {season}?",
        answer=f"{row['player']} with {row['total']} fours",
        category="batting_season_stat",
        season=season,
        cypher=cypher.strip(),
    )


def q_highest_individual_score(session, season: int) -> QAPair | None:
    cypher = """
        MATCH (p:Player)-[:BATTING_PERFORMANCE]->(bp:BattingPerformance)
              -[:PERFORMANCE_IN_INNINGS]->(i:Innings)<-[:HAS_INNINGS]-(m:Match)
        WHERE m.season = $season
        WITH p.name AS player, bp.runsScored AS runs, bp.ballsFaced AS balls
        ORDER BY runs DESC LIMIT 1
        RETURN player, runs, balls
    """
    row = session.run(cypher, season=season).single()
    if not row:
        return None
    return QAPair(
        question=f"What was the highest individual score in IPL {season}?",
        answer=f"{row['player']} scored {row['runs']} runs off {row['balls']} balls",
        category="batting_season_stat",
        season=season,
        cypher=cypher.strip(),
    )


def q_best_economy(session, season: int) -> QAPair | None:
    cypher = """
        MATCH (p:Player)-[:BOWLING_PERFORMANCE]->(bp:BowlingPerformance)
              -[:BOWLING_IN_INNINGS]->(i:Innings)<-[:HAS_INNINGS]-(m:Match)
        WHERE m.season = $season
        WITH p.name AS player,
             sum(bp.oversBowled) AS total_overs,
             sum(bp.runsConceded) AS total_runs
        WHERE total_overs >= $min_overs
        WITH player, round(toFloat(total_runs) / total_overs, 2) AS economy
        ORDER BY economy ASC LIMIT 1
        RETURN player, economy
    """
    row = session.run(cypher, season=season, min_overs=MIN_OVERS_BOWLED).single()
    if not row:
        return None
    return QAPair(
        question=f"Which bowler had the best economy rate in IPL {season} (minimum {int(MIN_OVERS_BOWLED)} overs)?",
        answer=f"{row['player']} with an economy of {row['economy']}",
        category="bowling_season_stat",
        season=season,
        cypher=cypher.strip(),
    )


def q_most_dot_balls(session, season: int) -> QAPair | None:
    cypher = """
        MATCH (p:Player)-[:BOWLING_PERFORMANCE]->(bp:BowlingPerformance)
              -[:BOWLING_IN_INNINGS]->(i:Innings)<-[:HAS_INNINGS]-(m:Match)
        WHERE m.season = $season
        WITH p.name AS player, sum(bp.dotBalls) AS total
        ORDER BY total DESC LIMIT 1
        RETURN player, total
    """
    row = session.run(cypher, season=season).single()
    if not row:
        return None
    return QAPair(
        question=f"Which bowler bowled the most dot balls in IPL {season}?",
        answer=f"{row['player']} with {row['total']} dot balls",
        category="bowling_season_stat",
        season=season,
        cypher=cypher.strip(),
    )


def q_team_wins(session, season: int) -> QAPair | None:
    cypher = """
        MATCH (t:Team)-[:WON_MATCH]->(m:Match)
        WHERE m.season = $season
        WITH t.name AS team, count(m) AS wins
        ORDER BY wins DESC LIMIT 1
        RETURN team, wins
    """
    row = session.run(cypher, season=season).single()
    if not row:
        return None
    return QAPair(
        question=f"Which team won the most matches in IPL {season}?",
        answer=f"{row['team']} with {row['wins']} wins",
        category="team_season_stat",
        season=season,
        cypher=cypher.strip(),
    )


def q_player_of_match_leader(session, season: int) -> QAPair | None:
    cypher = """
        MATCH (p:Player)-[:PLAYER_OF_MATCH]->(m:Match)
        WHERE m.season = $season
        WITH p.name AS player, count(m) AS awards
        ORDER BY awards DESC LIMIT 1
        RETURN player, awards
    """
    row = session.run(cypher, season=season).single()
    if not row:
        return None
    return QAPair(
        question=f"Who won the most Player of the Match awards in IPL {season}?",
        answer=f"{row['player']} with {row['awards']} awards",
        category="player_of_match",
        season=season,
        cypher=cypher.strip(),
    )


def q_most_caught_dismissals(session, season: int) -> QAPair | None:
    cypher = """
        MATCH (p:Player)-[:DISMISSED]->(w:Wicket)
              <-[:RESULTED_IN_WICKET]-(:Delivery)
              <-[:HAS_DELIVERY]-(:Over)
              <-[:HAS_OVER]-(i:Innings)
              <-[:HAS_INNINGS]-(m:Match)
        WHERE m.season = $season AND w.dismissalKind = 'caught'
        WITH p.name AS player, count(w) AS times
        ORDER BY times DESC LIMIT 1
        RETURN player, times
    """
    row = session.run(cypher, season=season).single()
    if not row:
        return None
    return QAPair(
        question=f"Which batsman was caught out the most times in IPL {season}?",
        answer=f"{row['player']} caught out {row['times']} times",
        category="dismissal_stat",
        season=season,
        cypher=cypher.strip(),
    )


def q_player_career_runs(session, player: str) -> QAPair | None:
    cypher = """
        MATCH (p:Player {name: $player})-[:BATTING_PERFORMANCE]->(bp:BattingPerformance)
        RETURN sum(bp.runsScored) AS total, count(bp) AS innings
    """
    row = session.run(cypher, player=player).single()
    if not row or not row["total"]:
        return None
    return QAPair(
        question=f"How many total runs did {player} score across all IPL seasons in this dataset?",
        answer=f"{row['total']} runs in {row['innings']} innings",
        category="career_stat",
        season=None,
        cypher=cypher.strip(),
    )


def q_player_career_wickets(session, player: str) -> QAPair | None:
    cypher = """
        MATCH (p:Player {name: $player})-[:BOWLING_PERFORMANCE]->(bp:BowlingPerformance)
        RETURN sum(bp.wicketsTaken) AS total, count(bp) AS innings
    """
    row = session.run(cypher, player=player).single()
    if not row or not row["total"]:
        return None
    return QAPair(
        question=f"How many total wickets did {player} take across all IPL seasons in this dataset?",
        answer=f"{row['total']} wickets in {row['innings']} innings",
        category="career_stat",
        season=None,
        cypher=cypher.strip(),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

# Season-level templates
SEASON_TEMPLATES = [
    q_top_run_scorer,
    q_top_wicket_taker,
    q_most_sixes,
    q_most_fours,
    q_highest_individual_score,
    q_best_economy,
    q_most_dot_balls,
    q_team_wins,
    q_player_of_match_leader,
    q_most_caught_dismissals,
]

# Top-N players to generate career stat questions for
TOP_PLAYERS_FOR_CAREER = 20


def generate_all(session) -> list[QAPair]:
    pairs: list[QAPair] = []

    seasons = fetch_seasons(session)
    print(f"Found seasons: {seasons}")

    # Season-level questions
    for season in seasons:
        for template_fn in SEASON_TEMPLATES:
            pair = template_fn(session, season)
            if pair:
                pairs.append(pair)
        print(f"  Season {season}: {sum(1 for p in pairs if p.season == season)} questions so far")

    # Career questions for top players by total runs
    print("\nGenerating career stat questions...")
    top_players_result = session.run("""
        MATCH (p:Player)-[:BATTING_PERFORMANCE]->(bp:BattingPerformance)
        WITH p.name AS player, sum(bp.runsScored) AS total
        ORDER BY total DESC LIMIT $n
        RETURN player
    """, n=TOP_PLAYERS_FOR_CAREER)
    top_batters = [r["player"] for r in top_players_result]

    top_bowlers_result = session.run("""
        MATCH (p:Player)-[:BOWLING_PERFORMANCE]->(bp:BowlingPerformance)
        WITH p.name AS player, sum(bp.wicketsTaken) AS total
        ORDER BY total DESC LIMIT $n
        RETURN player
    """, n=TOP_PLAYERS_FOR_CAREER)
    top_bowlers = [r["player"] for r in top_bowlers_result]

    for player in top_batters:
        pair = q_player_career_runs(session, player)
        if pair:
            pairs.append(pair)

    for player in top_bowlers:
        pair = q_player_career_wickets(session, player)
        if pair:
            pairs.append(pair)

    return pairs


def save_output(pairs: list[QAPair]) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"questions_{timestamp}.json"

    data = [asdict(p) for p in pairs]
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def main() -> None:
    driver = get_driver()
    try:
        with driver.session() as session:
            print("Generating Q&A pairs from Cricket KG...\n")
            pairs = generate_all(session)
    except AuthError:
        print("ERROR: Invalid Neo4j credentials.")
        sys.exit(1)
    except ServiceUnavailable:
        print("ERROR: Cannot reach Neo4j. Check NEO4J_URI and internet connection.")
        sys.exit(1)
    finally:
        driver.close()

    out_path = save_output(pairs)

    print(f"\n{'='*60}")
    print(f"Generated {len(pairs)} Q&A pairs")
    print(f"Saved to: {out_path}")
    print(f"{'='*60}")

    # Print a few samples
    print("\nSample questions:")
    for p in pairs[:5]:
        print(f"\n  Q: {p.question}")
        print(f"  A: {p.answer}")
        print(f"  Category: {p.category}")


if __name__ == "__main__":
    main()
