"""
Unit and integration tests for the Cricket KG RL environment.

Unit tests   — no network needed, run instantly
Integration  — need NEO4J_URI / NEO4J_PASSWORD in .env, marked with @pytest.mark.integration

Run unit tests only:
    uv run pytest tinker_cookbook/recipes/cricket_kg_rl/neo4j_env_test.py -v

Run all including integration:
    uv run pytest tinker_cookbook/recipes/cricket_kg_rl/neo4j_env_test.py -v -m integration
"""

from __future__ import annotations

import asyncio
import os

import pytest
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

from tinker_cookbook.recipes.cricket_kg_rl.neo4j_env import (
    Neo4jTools,
    _SCHEMA_CACHE,
    _fetch_schema,
    compute_reward,
)
from tinker_cookbook.tool_use.types import ToolInput

load_dotenv()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_driver():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    if not uri or not password:
        pytest.skip("NEO4J_URI / NEO4J_PASSWORD not set in .env")
    return AsyncGraphDatabase.driver(uri, auth=(user, password))


# ---------------------------------------------------------------------------
# Unit tests — compute_reward (pure, no network)
# ---------------------------------------------------------------------------

class TestComputeReward:
    def test_exact_match(self):
        reward, metrics = compute_reward(
            "DA Warner with 641 runs",
            "DA Warner with 641 runs",
        )
        assert reward == 1.0
        assert metrics["reward/number_match"] == 1.0
        assert metrics["reward/entity_match"] == 1.0

    def test_correct_number_correct_entity(self):
        # Model may phrase it differently but gets the right number + entity
        reward, _ = compute_reward(
            "The top scorer was DA Warner who scored 641 runs in IPL 2017",
            "DA Warner with 641 runs",
        )
        assert reward == 1.0

    def test_wrong_number(self):
        reward, metrics = compute_reward(
            "DA Warner with 600 runs",
            "DA Warner with 641 runs",
        )
        assert reward == 0.0
        assert metrics["reward/number_match"] == 0.0

    def test_wrong_entity(self):
        reward, metrics = compute_reward(
            "RG Sharma with 641 runs",
            "DA Warner with 641 runs",
        )
        assert reward == 0.0
        assert metrics["reward/entity_match"] == 0.0

    def test_no_answer_submitted(self):
        reward, metrics = compute_reward(None, "DA Warner with 641 runs")
        assert reward == 0.0
        assert metrics["reward/no_answer"] == 1.0

    def test_team_question(self):
        reward, _ = compute_reward(
            "Mumbai Indians won 8 matches",
            "Mumbai Indians with 8 wins",
        )
        assert reward == 1.0

    def test_bowling_question(self):
        reward, _ = compute_reward(
            "B Kumar took the most wickets: 28",
            "B Kumar with 28 wickets",
        )
        assert reward == 1.0

    def test_case_insensitive(self):
        reward, _ = compute_reward(
            "da warner scored 641 runs",
            "DA Warner with 641 runs",
        )
        assert reward == 1.0


# ---------------------------------------------------------------------------
# Unit tests — run_cypher write blocking (no network)
# ---------------------------------------------------------------------------

class TestRunCypherWriteBlocking:
    """Verify that write Cypher operations are blocked without hitting Neo4j."""

    def _make_tools_no_driver(self):
        # driver=None is fine here since we never execute the query
        return Neo4jTools(driver=None)  # type: ignore[arg-type]

    @pytest.mark.parametrize("query", [
        "CREATE (n:Player {name: 'test'})",
        "MERGE (n:Team {name: 'X'})",
        "MATCH (n) DELETE n",
        "MATCH (n) SET n.name = 'hack'",
        "MATCH (n) REMOVE n.name",
        "DROP INDEX player_name",
    ])
    def test_write_queries_blocked(self, query: str):
        tools = self._make_tools_no_driver()
        result = asyncio.run(tools.run_cypher.run(ToolInput(arguments={"query": query})))
        content = result.messages[0]["content"]
        assert "write" in content.lower() or "error" in content.lower()
        assert result.should_stop is False


# ---------------------------------------------------------------------------
# Unit tests — final_answer tool (no network)
# ---------------------------------------------------------------------------

class TestFinalAnswerTool:
    def test_final_answer_stops_episode(self):
        tools = Neo4jTools(driver=None)  # type: ignore[arg-type]
        result = asyncio.run(
            tools.final_answer.run(ToolInput(arguments={"answer": "DA Warner with 641 runs"}))
        )
        assert result.should_stop is True
        assert result.messages[0]["content"] == "Answer recorded."

    def test_final_answer_stores_text(self):
        tools = Neo4jTools(driver=None)  # type: ignore[arg-type]
        asyncio.run(
            tools.final_answer.run(ToolInput(arguments={"answer": "Mumbai Indians with 8 wins"}))
        )
        assert tools._final_answer == "Mumbai Indians with 8 wins"


# ---------------------------------------------------------------------------
# Integration tests — real AuraDB connection
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestNeo4jToolsIntegration:
    """Requires live AuraDB. Run with: pytest -m integration"""

    def test_get_schema_returns_node_labels(self):
        driver = _make_driver()

        async def run():
            tools = Neo4jTools(driver=driver)
            result = await tools.get_schema.run(ToolInput(arguments={}))
            await driver.close()
            return result

        result = asyncio.run(run())
        content = result.messages[0]["content"]
        assert "Player" in content
        assert "Match" in content
        assert "BattingPerformance" in content
        assert result.should_stop is False

    def test_get_schema_returns_relationship_types(self):
        driver = _make_driver()

        async def run():
            tools = Neo4jTools(driver=driver)
            result = await tools.get_schema.run(ToolInput(arguments={}))
            await driver.close()
            return result

        result = asyncio.run(run())
        content = result.messages[0]["content"]
        assert "BATTING_PERFORMANCE" in content
        assert "HAS_INNINGS" in content

    def test_run_cypher_simple_query(self):
        driver = _make_driver()

        async def run():
            tools = Neo4jTools(driver=driver)
            result = await tools.run_cypher.run(
                ToolInput(arguments={"query": "MATCH (p:Player) RETURN p.name AS name LIMIT 3"})
            )
            await driver.close()
            return result

        result = asyncio.run(run())
        content = result.messages[0]["content"]
        assert "name" in content
        assert result.should_stop is False

    def test_run_cypher_aggregation(self):
        """Verify a real aggregation query — the kind the agent will write."""
        driver = _make_driver()

        async def run():
            tools = Neo4jTools(driver=driver)
            result = await tools.run_cypher.run(ToolInput(arguments={"query": """
                MATCH (p:Player)-[:BATTING_PERFORMANCE]->(bp:BattingPerformance)
                      -[:PERFORMANCE_IN_INNINGS]->(i:Innings)<-[:HAS_INNINGS]-(m:Match)
                WHERE m.season = '2017'
                WITH p.name AS player, sum(bp.runsScored) AS total
                ORDER BY total DESC LIMIT 1
                RETURN player, total
            """}))
            await driver.close()
            return result

        result = asyncio.run(run())
        content = result.messages[0]["content"]
        # DA Warner was top scorer in 2017
        assert "Warner" in content
        assert "641" in content

    def test_run_cypher_syntax_error_returns_error_not_exception(self):
        """Bad Cypher should return an error message, not crash."""
        driver = _make_driver()

        async def run():
            tools = Neo4jTools(driver=driver)
            result = await tools.run_cypher.run(
                ToolInput(arguments={"query": "THIS IS NOT CYPHER $$$$"})
            )
            await driver.close()
            return result

        result = asyncio.run(run())
        content = result.messages[0]["content"]
        assert "error" in content.lower()
        assert result.should_stop is False
