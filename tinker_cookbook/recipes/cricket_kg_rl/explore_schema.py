"""
Explore the Neo4j AuraDB schema for the T20 cricket knowledge graph.

Run this first before building any question templates or the RL environment.
It prints node labels, relationship types, their properties, and row counts.
Output is written to output/schema_<timestamp>.txt alongside terminal stdout.

Usage:
    uv run python -m tinker_cookbook.recipes.cricket_kg_rl.explore_schema

Requires in your .env file:
    NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=your_password
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

load_dotenv()

OUTPUT_DIR = Path(__file__).parent / "output"


def _make_output_file() -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"schema_{timestamp}.txt"


class _Tee:
    """Write to both stdout and a file simultaneously."""

    def __init__(self, filepath: Path) -> None:
        self._file = filepath.open("w", encoding="utf-8")
        self._stdout = sys.stdout

    def write(self, data: str) -> None:
        self._stdout.write(data)
        self._file.write(data)

    def flush(self) -> None:
        self._stdout.flush()
        self._file.flush()

    def close(self) -> None:
        self._file.close()


def get_driver():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")

    if not uri or not password:
        print("ERROR: NEO4J_URI and NEO4J_PASSWORD must be set in your .env file.")
        sys.exit(1)

    return GraphDatabase.driver(uri, auth=(user, password))


def print_node_schema(session) -> None:
    print("=" * 60)
    print("NODE LABELS & PROPERTIES")
    print("=" * 60)
    result = session.run("""
        CALL db.schema.nodeTypeProperties()
        YIELD nodeType, propertyName, propertyTypes
        RETURN nodeType, collect(propertyName) AS properties
        ORDER BY nodeType
    """)
    for r in result:
        print(f"  {r['nodeType']}")
        for prop in r["properties"]:
            print(f"      .{prop}")


def print_relationship_schema(session) -> None:
    print("\n" + "=" * 60)
    print("RELATIONSHIP TYPES & PROPERTIES")
    print("=" * 60)
    result = session.run("""
        CALL db.schema.relTypeProperties()
        YIELD relType, propertyName
        RETURN relType, collect(propertyName) AS properties
        ORDER BY relType
    """)
    for r in result:
        print(f"  {r['relType']}")
        for prop in r["properties"]:
            print(f"      .{prop}")


def print_node_counts(session) -> None:
    print("\n" + "=" * 60)
    print("NODE COUNTS PER LABEL")
    print("=" * 60)
    result = session.run("""
        CALL db.labels() YIELD label
        CALL apoc.cypher.run(
            'MATCH (n:' + label + ') RETURN count(n) AS count', {}
        ) YIELD value
        RETURN label, value.count AS count
        ORDER BY count DESC
    """)
    rows = list(result)
    if not rows:
        # fallback if APOC not available
        print("  (APOC not available — skipping counts)")
        return
    for r in rows:
        print(f"  {r['label']}: {r['count']:,}")


def print_relationship_counts(session) -> None:
    print("\n" + "=" * 60)
    print("RELATIONSHIP COUNTS PER TYPE")
    print("=" * 60)
    result = session.run("""
        CALL db.relationshipTypes() YIELD relationshipType
        CALL apoc.cypher.run(
            'MATCH ()-[r:' + relationshipType + ']->() RETURN count(r) AS count', {}
        ) YIELD value
        RETURN relationshipType, value.count AS count
        ORDER BY count DESC
    """)
    rows = list(result)
    if not rows:
        print("  (APOC not available — skipping counts)")
        return
    for r in rows:
        print(f"  {r['relationshipType']}: {r['count']:,}")


def print_sample_nodes(session) -> None:
    """Print one sample node per label so we can see real property values."""
    print("\n" + "=" * 60)
    print("SAMPLE NODE (1 per label)")
    print("=" * 60)
    labels_result = session.run("CALL db.labels() YIELD label RETURN label ORDER BY label")
    labels = [r["label"] for r in labels_result]
    for label in labels:
        result = session.run(f"MATCH (n:`{label}`) RETURN properties(n) AS props LIMIT 1")
        row = result.single()
        if row:
            print(f"\n  [{label}]")
            for k, v in row["props"].items():
                print(f"      {k}: {v}")


def main() -> None:
    out_path = _make_output_file()
    tee = _Tee(out_path)
    sys.stdout = tee  # type: ignore[assignment]

    try:
        print(f"schema exploration — {datetime.now().isoformat()}")
        print(f"output file: {out_path}\n")

        driver = get_driver()
        try:
            with driver.session() as session:
                print_node_schema(session)
                print_relationship_schema(session)
                print_node_counts(session)
                print_relationship_counts(session)
                print_sample_nodes(session)
        except AuthError:
            print("ERROR: Invalid Neo4j credentials. Check NEO4J_USER and NEO4J_PASSWORD in .env")
            sys.exit(1)
        except ServiceUnavailable:
            print("ERROR: Cannot reach Neo4j. Check NEO4J_URI in .env and your internet connection.")
            sys.exit(1)
        finally:
            driver.close()

        print("\n" + "=" * 60)
        print("Done.")
        print("=" * 60)

    finally:
        sys.stdout = tee._stdout
        tee.close()
        print(f"\nOutput saved to: {out_path}")


if __name__ == "__main__":
    main()
